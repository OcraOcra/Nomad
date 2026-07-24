"""MCP data ingestor with parallel execution."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from .wrappers import NewsWrapper, IntelWrapper, IMFWrapper

logger = logging.getLogger(__name__)


def ingest_mcp_sources(
    output_dir: Path = Path("data/raw/mcp"),
    timeout: int = 30,
    max_workers: int = 3,
) -> Dict[str, Any]:
    """
    Fetch data from all enabled MCP sources in parallel.
    
    Executes all MCP wrappers concurrently using ThreadPoolExecutor.
    Each wrapper's errors are captured independently without stopping others.
    
    Args:
        output_dir: Directory to save MCP data files
        timeout: Timeout in seconds for each wrapper
        max_workers: Maximum number of parallel threads
    
    Returns:
        Dictionary with consolidated data from all sources
    
    Example:
        >>> data = ingest_mcp_sources()
        >>> print(data["news"]["breaking_news"])
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize wrappers
    wrappers = {
        "news": NewsWrapper(timeout=timeout),
        "world_intel": IntelWrapper(timeout=timeout),
        "imf": IMFWrapper(timeout=timeout),
    }
    
    results = {}
    
    # Execute wrappers in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_source = {
            executor.submit(wrapper.fetch): source_name
            for source_name, wrapper in wrappers.items()
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_source):
            source_name = future_to_source[future]
            try:
                data = future.result()
                results[source_name] = data
                logger.info(f"MCP source '{source_name}' fetched successfully")
            except Exception as e:
                error_msg = str(e)
                results[source_name] = {"error": error_msg}
                logger.error(f"MCP source '{source_name}' failed: {error_msg}")
    
    # Add metadata
    timestamp = datetime.now().isoformat()
    consolidated = {
        "timestamp": timestamp,
        "sources": results,
        "metadata": {
            "total_sources": len(wrappers),
            "successful": sum(1 for r in results.values() if "error" not in r),
            "failed": sum(1 for r in results.values() if "error" in r),
        }
    }
    
    # Save timestamped file
    timestamp_file = output_dir / f"mcp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(timestamp_file, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2, ensure_ascii=False)
    logger.info(f"MCP data saved to {timestamp_file}")
    
    # Update latest file
    latest_file = output_dir / "mcp_latest.json"
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2, ensure_ascii=False)
    
    return consolidated
