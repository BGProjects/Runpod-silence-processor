#!/usr/bin/env python3
"""
Test script to demonstrate the multiprocessing silence detection functionality
"""

import os
import sys
import logging
import time
from silence_serverless_r2 import SilenceProcessorR2

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_multiprocessing_performance():
    """Test and compare single-threaded vs multiprocessing performance"""
    
    # Test with available audio file
    test_file = "test_small.wav"
    
    if not os.path.exists(test_file):
        logger.error(f"Test audio file not found: {test_file}")
        return
    
    logger.info("🚀 Starting multiprocessing silence detection test...")
    logger.info(f"📁 Test file: {test_file}")
    
    # Create processor (we'll use methods directly, not the full R2 pipeline)
    processor = SilenceProcessorR2()
    
    try:
        # Test 1: Single-threaded processing
        logger.info("\n" + "="*60)
        logger.info("📊 TEST 1: Single-threaded processing")
        logger.info("="*60)
        
        start_time = time.perf_counter()
        single_result = processor._detect_silence_segments_fast(test_file)
        single_time = time.perf_counter() - start_time
        
        logger.info(f"✅ Single-threaded completed: {single_time:.3f}s")
        logger.info(f"   Found {single_result['segment_count']} silence segments")
        logger.info(f"   Audio duration: {single_result['audio_duration']}")
        logger.info(f"   Silence percentage: {single_result['silence_percentage']}%")
        
        # Test 2: Multiprocessing
        logger.info("\n" + "="*60)
        logger.info("🚀 TEST 2: Multiprocessing")  
        logger.info("="*60)
        
        start_time = time.perf_counter()
        multi_result = processor._detect_silence_segments_multiprocessing(test_file, use_multiprocessing=True)
        multi_time = time.perf_counter() - start_time
        
        logger.info(f"✅ Multiprocessing completed: {multi_time:.3f}s")
        logger.info(f"   Found {multi_result['segment_count']} silence segments")
        logger.info(f"   Processing method: {multi_result.get('processing_method', 'N/A')}")
        logger.info(f"   Processes used: {multi_result.get('params', {}).get('num_processes', 'N/A')}")
        
        # Test 3: Auto-detect best method
        logger.info("\n" + "="*60)
        logger.info("🤖 TEST 3: Auto-detect best method")
        logger.info("="*60)
        
        start_time = time.perf_counter()
        auto_result = processor.detect_silence_segments(test_file, use_multiprocessing=None)
        auto_time = time.perf_counter() - start_time
        
        logger.info(f"✅ Auto-detect completed: {auto_time:.3f}s")
        logger.info(f"   Method selected: {auto_result.get('processing_method', 'N/A')}")
        logger.info(f"   Found {auto_result['segment_count']} silence segments")
        
        # Test 4: Benchmark comparison
        logger.info("\n" + "="*60)
        logger.info("🏁 TEST 4: Benchmark comparison")
        logger.info("="*60)
        
        benchmark_result = processor.detect_silence_segments(test_file, run_benchmark=True)
        
        if 'error' not in benchmark_result:
            perf = benchmark_result['performance']
            logger.info(f"🏆 Benchmark Results:")
            logger.info(f"   Speedup: {perf['speedup_factor']}x faster")
            logger.info(f"   Time saved: {perf['time_saved_seconds']}s ({perf['time_saved_percentage']}%)")
            logger.info(f"   Results identical: {perf['results_identical']}")
        else:
            logger.error(f"Benchmark failed: {benchmark_result['error']}")
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("📋 SUMMARY")
        logger.info("="*60)
        
        speedup = single_time / multi_time if multi_time > 0 else 0
        
        logger.info(f"Single-threaded: {single_time:.3f}s")
        logger.info(f"Multiprocessing:  {multi_time:.3f}s") 
        logger.info(f"Speedup:         {speedup:.2f}x")
        logger.info(f"Results match:   {single_result['segment_count'] == multi_result['segment_count']}")
        
        # Verify results are identical
        single_segments = single_result.get('silences', [])
        multi_segments = multi_result.get('silences', [])
        
        if len(single_segments) == len(multi_segments):
            logger.info("✅ Both methods found the same number of segments")
            
            # Check first few segments for timing accuracy (allow small differences due to floating point)
            max_check = min(3, len(single_segments))
            timing_match = True
            
            for i in range(max_check):
                s1, s2 = single_segments[i], multi_segments[i]
                start_diff = abs(s1['start_ms'] - s2['start_ms'])
                end_diff = abs(s1['end_ms'] - s2['end_ms'])
                
                if start_diff > 1 or end_diff > 1:  # Allow 1ms difference
                    timing_match = False
                    logger.warning(f"⚠️  Segment {i+1} timing difference: start={start_diff:.1f}ms, end={end_diff:.1f}ms")
            
            if timing_match:
                logger.info("✅ Segment timings match within acceptable tolerance")
            
        else:
            logger.warning(f"⚠️  Segment count mismatch: single={len(single_segments)}, multi={len(multi_segments)}")
            
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_multiprocessing_performance()