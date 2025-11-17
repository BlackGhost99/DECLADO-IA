"""
Performance Tests - CPU/Memory Profiling, Latency, Batch Processing
Phase 10: Tests, QA et Performance
"""

import csv
import io
import time
from decimal import Decimal
from pathlib import Path

import pytest
import psutil
import os

from app.rules_engine import CalculationInput, CustomsCalculator
from app.ocr_pipeline import pipeline as ocr_pipeline


# ============================================================================
# Performance Fixtures
# ============================================================================


@pytest.fixture
def performance_monitor():
    """Monitor CPU and memory usage during tests."""
    process = psutil.Process(os.getpid())

    class Monitor:
        def __init__(self):
            self.start_cpu = None
            self.start_memory = None
            self.peak_memory = 0
            self.measurements = []

        def start(self):
            self.start_cpu = process.cpu_percent(interval=0.1)
            self.start_memory = process.memory_info().rss / 1024 / 1024  # MB
            self.peak_memory = self.start_memory

        def sample(self):
            """Take a sample of current resource usage."""
            cpu = process.cpu_percent(interval=0.1)
            memory = process.memory_info().rss / 1024 / 1024  # MB
            self.peak_memory = max(self.peak_memory, memory)
            self.measurements.append({"cpu": cpu, "memory": memory, "time": time.time()})

        def stop(self):
            """Stop monitoring and return final stats."""
            final_cpu = process.cpu_percent(interval=0.1)
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            self.peak_memory = max(self.peak_memory, final_memory)

            return {
                "start_cpu": self.start_cpu,
                "final_cpu": final_cpu,
                "start_memory_mb": self.start_memory,
                "final_memory_mb": final_memory,
                "peak_memory_mb": self.peak_memory,
                "memory_delta_mb": final_memory - self.start_memory,
                "samples": len(self.measurements),
            }

    return Monitor()


# ============================================================================
# Latency Tests - Inference Speed
# ============================================================================


@pytest.mark.performance
def test_calculation_latency_single(performance_monitor):
    """Test latency of single customs calculation."""
    calculator = CustomsCalculator()

    calc_input = CalculationInput(
        invoice_number="PERF-001",
        hs_code="6109",
        description="T-shirt en coton",
        quantity=Decimal("100"),
        unit_price=Decimal("5.50"),
        currency="EUR",
        incoterm="CIF",
        origin_country="CN",
        destination_country="CM",
        exchange_rate=Decimal("655.957"),
    )

    performance_monitor.start()

    start_time = time.perf_counter()
    result = calculator.calculate(calc_input)
    end_time = time.perf_counter()

    stats = performance_monitor.stop()
    latency_ms = (end_time - start_time) * 1000

    # Assertions
    assert latency_ms < 2000, f"Calculation too slow: {latency_ms:.2f}ms (target: <2s)"
    assert result.calculation_id, "Calculation ID missing"

    print(f"⏱️  Single calculation latency: {latency_ms:.2f}ms")
    print(f"💾 Memory usage: {stats['peak_memory_mb']:.2f} MB")


@pytest.mark.performance
def test_calculation_latency_batch_10(performance_monitor):
    """Test latency of 10 sequential calculations."""
    calculator = CustomsCalculator()

    calc_inputs = [
        CalculationInput(
            invoice_number=f"PERF-BATCH-{i:03d}",
            hs_code="6109",
            description=f"Product {i}",
            quantity=Decimal("100"),
            unit_price=Decimal("5.50"),
            currency="EUR",
            incoterm="CIF",
            origin_country="CN",
            destination_country="CM",
        )
        for i in range(10)
    ]

    performance_monitor.start()

    start_time = time.perf_counter()
    results = [calculator.calculate(inp) for inp in calc_inputs]
    end_time = time.perf_counter()

    stats = performance_monitor.stop()
    total_time_ms = (end_time - start_time) * 1000
    avg_latency_ms = total_time_ms / len(calc_inputs)

    # Assertions
    assert len(results) == 10, "Not all calculations completed"
    assert avg_latency_ms < 2000, f"Average latency too high: {avg_latency_ms:.2f}ms"
    assert stats["peak_memory_mb"] < 2000, f"Memory usage too high: {stats['peak_memory_mb']:.2f} MB"

    print(f"⏱️  10 calculations: {total_time_ms:.2f}ms total, {avg_latency_ms:.2f}ms avg")
    print(f"💾 Peak memory: {stats['peak_memory_mb']:.2f} MB")


@pytest.mark.performance
@pytest.mark.slow
def test_calculation_latency_batch_200(performance_monitor):
    """
    Test batch processing of 200 items (target: < 30 minutes).

    This is a critical performance test for production workloads.
    """
    calculator = CustomsCalculator()

    # Generate 200 calculation inputs
    calc_inputs = [
        CalculationInput(
            invoice_number=f"BATCH-{i:03d}",
            hs_code="6109" if i % 2 == 0 else "6204",
            description=f"Product batch item {i}",
            quantity=Decimal(str(50 + (i % 100))),
            unit_price=Decimal(str(5.0 + (i % 50) * 0.1)),
            currency="EUR" if i % 3 == 0 else "USD",
            incoterm="CIF" if i % 2 == 0 else "FOB",
            origin_country="CN",
            destination_country="CM",
        )
        for i in range(200)
    ]

    performance_monitor.start()

    start_time = time.perf_counter()
    results = []
    errors = 0

    for idx, calc_input in enumerate(calc_inputs):
        try:
            result = calculator.calculate(calc_input)
            results.append(result)
        except Exception as e:
            errors += 1
            print(f"Error on item {idx}: {e}")

        # Sample every 20 items
        if idx % 20 == 0:
            performance_monitor.sample()

    end_time = time.perf_counter()

    stats = performance_monitor.stop()
    total_time_seconds = end_time - start_time
    total_time_minutes = total_time_seconds / 60
    avg_latency_ms = (total_time_seconds * 1000) / len(calc_inputs)

    # Assertions
    assert len(results) >= 190, f"Success rate too low: {len(results)}/200 (target: ≥95%)"
    assert errors <= 10, f"Too many errors: {errors}/200"
    assert total_time_minutes < 30, f"Batch processing too slow: {total_time_minutes:.2f} min (target: <30 min)"
    assert stats["peak_memory_mb"] < 3000, f"Memory usage too high: {stats['peak_memory_mb']:.2f} MB"

    print(f"\n✅ Batch 200 items completed:")
    print(f"   ⏱️  Total time: {total_time_minutes:.2f} minutes ({total_time_seconds:.2f}s)")
    print(f"   ⏱️  Average latency: {avg_latency_ms:.2f}ms per item")
    print(f"   📊 Success rate: {len(results)}/200 ({len(results)/200*100:.1f}%)")
    print(f"   ❌ Errors: {errors}")
    print(f"   💾 Peak memory: {stats['peak_memory_mb']:.2f} MB")
    print(f"   💾 Memory delta: {stats['memory_delta_mb']:.2f} MB")


# ============================================================================
# CPU & Memory Profiling
# ============================================================================


@pytest.mark.performance
def test_cpu_usage_during_calculation(performance_monitor):
    """Test CPU usage during calculation operations."""
    calculator = CustomsCalculator()

    calc_input = CalculationInput(
        invoice_number="CPU-TEST",
        hs_code="6109",
        description="CPU profiling test",
        quantity=Decimal("1000"),
        unit_price=Decimal("10.00"),
        currency="USD",
        incoterm="FOB",
        origin_country="CN",
        destination_country="CM",
    )

    performance_monitor.start()

    # Run multiple calculations
    for _ in range(50):
        calculator.calculate(calc_input)
        performance_monitor.sample()

    stats = performance_monitor.stop()

    # Assertions
    avg_cpu = sum(m["cpu"] for m in performance_monitor.measurements) / len(performance_monitor.measurements)
    assert avg_cpu < 80, f"Average CPU usage too high: {avg_cpu:.1f}% (target: <80%)"

    print(f"💻 Average CPU usage: {avg_cpu:.1f}%")
    print(f"💻 Peak CPU: {max(m['cpu'] for m in performance_monitor.measurements):.1f}%")
    print(f"💾 Memory: {stats['peak_memory_mb']:.2f} MB")


@pytest.mark.performance
def test_memory_leak_detection(performance_monitor):
    """Test for memory leaks by running many calculations."""
    calculator = CustomsCalculator()

    calc_input = CalculationInput(
        invoice_number="MEM-TEST",
        hs_code="6109",
        description="Memory leak test",
        quantity=Decimal("100"),
        unit_price=Decimal("5.00"),
        currency="EUR",
        incoterm="CIF",
        origin_country="CN",
        destination_country="CM",
    )

    performance_monitor.start()
    initial_memory = performance_monitor.start_memory

    # Run 100 calculations
    for i in range(100):
        calculator.calculate(calc_input)
        if i % 10 == 0:
            performance_monitor.sample()

    stats = performance_monitor.stop()
    memory_growth = stats["memory_delta_mb"]

    # Assertions
    # Allow up to 100MB growth (acceptable for 100 calculations)
    assert memory_growth < 100, f"Potential memory leak: {memory_growth:.2f} MB growth (target: <100MB)"

    print(f"💾 Initial memory: {initial_memory:.2f} MB")
    print(f"💾 Final memory: {stats['final_memory_mb']:.2f} MB")
    print(f"💾 Memory growth: {memory_growth:.2f} MB")
    print(f"💾 Peak memory: {stats['peak_memory_mb']:.2f} MB")


# ============================================================================
# OCR Pipeline Performance
# ============================================================================


@pytest.mark.performance
@pytest.mark.requires_tesseract
def test_ocr_latency_single_image(temp_image_file, performance_monitor):
    """Test OCR processing latency for single image."""
    performance_monitor.start()

    start_time = time.perf_counter()
    result = ocr_pipeline.run_document(temp_image_file, lang="eng+fra")
    end_time = time.perf_counter()

    stats = performance_monitor.stop()
    latency_seconds = end_time - start_time

    # Assertions
    assert latency_seconds < 10, f"OCR too slow: {latency_seconds:.2f}s (target: <10s)"
    assert "source" in result
    assert "pages" in result

    print(f"⏱️  OCR latency: {latency_seconds:.2f}s")
    print(f"💾 Memory: {stats['peak_memory_mb']:.2f} MB")


# ============================================================================
# API Endpoint Performance
# ============================================================================


@pytest.mark.performance
def test_api_calculate_endpoint_latency(client, performance_monitor):
    """Test API endpoint latency for calculation."""
    calc_request = {
        "invoice_number": "API-PERF-001",
        "hs_code": "6109",
        "description": "API performance test",
        "quantity": 100,
        "unit_price": 5.50,
        "currency": "EUR",
        "incoterm": "CIF",
        "origin_country": "CN",
        "destination_country": "CM",
    }

    performance_monitor.start()

    start_time = time.perf_counter()
    response = client.post("/api/customs/calculate", json=calc_request)
    end_time = time.perf_counter()

    stats = performance_monitor.stop()
    latency_ms = (end_time - start_time) * 1000

    # Assertions
    assert response.status_code == 200, f"API returned {response.status_code}"
    assert latency_ms < 3000, f"API too slow: {latency_ms:.2f}ms (target: <3s)"

    print(f"⏱️  API endpoint latency: {latency_ms:.2f}ms")
    print(f"💾 Memory: {stats['peak_memory_mb']:.2f} MB")


@pytest.mark.performance
@pytest.mark.slow
def test_api_batch_processing_200(client, performance_monitor):
    """Test API batch processing of 200 items via HTTP."""
    # Generate batch data
    batch_requests = [
        {
            "invoice_number": f"API-BATCH-{i:03d}",
            "hs_code": "6109" if i % 2 == 0 else "6204",
            "description": f"Product {i}",
            "quantity": 50 + (i % 100),
            "unit_price": 5.0 + (i % 50) * 0.1,
            "currency": "EUR" if i % 3 == 0 else "USD",
            "incoterm": "CIF" if i % 2 == 0 else "FOB",
            "origin_country": "CN",
            "destination_country": "CM",
        }
        for i in range(200)
    ]

    performance_monitor.start()

    start_time = time.perf_counter()
    results = []
    errors = 0

    for idx, request in enumerate(batch_requests):
        response = client.post("/api/customs/calculate", json=request)

        if response.status_code == 200:
            results.append(response.json())
        else:
            errors += 1

        if idx % 20 == 0:
            performance_monitor.sample()

    end_time = time.perf_counter()

    stats = performance_monitor.stop()
    total_time_seconds = end_time - start_time
    total_time_minutes = total_time_seconds / 60

    # Assertions
    assert len(results) >= 190, f"Success rate too low: {len(results)}/200"
    assert total_time_minutes < 30, f"Batch API too slow: {total_time_minutes:.2f} min"

    print(f"\n✅ API Batch 200 items:")
    print(f"   ⏱️  Total time: {total_time_minutes:.2f} minutes")
    print(f"   📊 Success: {len(results)}/200")
    print(f"   ❌ Errors: {errors}")
    print(f"   💾 Peak memory: {stats['peak_memory_mb']:.2f} MB")


# ============================================================================
# Throughput Tests
# ============================================================================


@pytest.mark.performance
def test_calculation_throughput(performance_monitor):
    """Test calculations per second (throughput)."""
    calculator = CustomsCalculator()

    calc_input = CalculationInput(
        invoice_number="THROUGHPUT",
        hs_code="6109",
        description="Throughput test",
        quantity=Decimal("100"),
        unit_price=Decimal("5.00"),
        currency="EUR",
        incoterm="CIF",
        origin_country="CN",
        destination_country="CM",
    )

    performance_monitor.start()

    num_calculations = 100
    start_time = time.perf_counter()

    for _ in range(num_calculations):
        calculator.calculate(calc_input)

    end_time = time.perf_counter()

    stats = performance_monitor.stop()
    total_time = end_time - start_time
    throughput = num_calculations / total_time

    # Assertions
    assert throughput > 10, f"Throughput too low: {throughput:.2f} calc/s (target: >10 calc/s)"

    print(f"🚀 Throughput: {throughput:.2f} calculations/second")
    print(f"⏱️  Total time: {total_time:.2f}s for {num_calculations} calculations")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "performance"])

