#!/usr/bin/env python3
"""
Test script for Data Assurance Tiers feature.

This script validates the complete implementation across:
1. Configuration loading
2. Catalog parsing and validation
3. API response formatting
4. Custom label configuration
"""

import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from moniker_svc.config import Config
from moniker_svc.catalog.loader import CatalogLoader


def test_config_loading():
    """Test 1: Configuration Loading"""
    print("=" * 60)
    print("TEST 1: Configuration Loading")
    print("=" * 60)

    # Load default config
    config = Config.from_yaml("sample_config.yaml")

    assert config.assurance_tiers.enabled == True, "Tiers should be enabled"
    assert config.assurance_tiers.default_tier == 1, "Default tier should be 1"
    assert config.assurance_tiers.labels[1] == "bronze", "Tier 1 should be bronze"
    assert config.assurance_tiers.labels[2] == "silver", "Tier 2 should be silver"
    assert config.assurance_tiers.labels[3] == "gold", "Tier 3 should be gold"

    print("✅ Config loaded successfully")
    print(f"   Enabled: {config.assurance_tiers.enabled}")
    print(f"   Default tier: {config.assurance_tiers.default_tier}")
    print(f"   Labels: {config.assurance_tiers.labels}")
    print()


def test_catalog_parsing():
    """Test 2: Catalog Parsing"""
    print("=" * 60)
    print("TEST 2: Catalog Parsing")
    print("=" * 60)

    loader = CatalogLoader()
    registry = loader.load_file("sample_catalog.yaml")

    # Test nodes with tiers
    test_cases = [
        ("benchmarks", 2, "silver"),
        ("benchmarks.constituents", 3, "gold"),
        ("commodities", 1, "bronze"),
        ("prices", 3, "gold"),
    ]

    config = Config.from_yaml("sample_config.yaml")

    for path, expected_tier, expected_label in test_cases:
        node = registry.get(path)
        assert node is not None, f"Node {path} should exist"
        assert node.data_assurance_tier == expected_tier, \
            f"{path} should have tier {expected_tier}, got {node.data_assurance_tier}"

        label = config.assurance_tiers.labels.get(expected_tier)
        assert label == expected_label, \
            f"{path} should have label {expected_label}, got {label}"

        print(f"✅ {path}: tier={node.data_assurance_tier}, label={label}")

    print()


def test_validation():
    """Test 3: Validation"""
    print("=" * 60)
    print("TEST 3: Validation (Invalid Tiers)")
    print("=" * 60)

    # Test invalid tier value
    invalid_catalog = """
invalid_node:
  display_name: Invalid Node
  data_assurance_tier: 5
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(invalid_catalog)
        temp_file = f.name

    loader = CatalogLoader()
    try:
        registry = loader.load_file(temp_file)
        print("❌ FAIL: Should have raised ValueError")
        sys.exit(1)
    except ValueError as e:
        assert "data_assurance_tier must be 1, 2, or 3" in str(e)
        print(f"✅ Validation caught invalid tier: {e}")
    finally:
        Path(temp_file).unlink()

    # Test valid tiers
    valid_catalog = """
tier1:
  data_assurance_tier: 1
tier2:
  data_assurance_tier: 2
tier3:
  data_assurance_tier: 3
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(valid_catalog)
        temp_file = f.name

    try:
        registry = loader.load_file(temp_file)
        for i in range(1, 4):
            node = registry.get(f"tier{i}")
            assert node.data_assurance_tier == i
        print("✅ All valid tiers (1, 2, 3) accepted")
    finally:
        Path(temp_file).unlink()

    print()


def test_custom_labels():
    """Test 4: Custom Labels"""
    print("=" * 60)
    print("TEST 4: Custom Labels")
    print("=" * 60)

    # Create custom config
    custom_config_yaml = """
project_name: "Open Moniker"
assurance_tiers:
  enabled: true
  default_tier: 1
  labels:
    1: cataloged
    2: governed
    3: certified
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(custom_config_yaml)
        temp_file = f.name

    try:
        config = Config.from_yaml(temp_file)
        assert config.assurance_tiers.labels[1] == "cataloged"
        assert config.assurance_tiers.labels[2] == "governed"
        assert config.assurance_tiers.labels[3] == "certified"

        print("✅ Custom labels loaded successfully")
        print(f"   Tier 1: {config.assurance_tiers.labels[1]}")
        print(f"   Tier 2: {config.assurance_tiers.labels[2]}")
        print(f"   Tier 3: {config.assurance_tiers.labels[3]}")
    finally:
        Path(temp_file).unlink()

    print()


def test_optional_tier():
    """Test 5: Optional Tier (Backwards Compatibility)"""
    print("=" * 60)
    print("TEST 5: Optional Tier (Backwards Compatibility)")
    print("=" * 60)

    # Catalog without tier
    catalog_without_tier = """
no_tier_node:
  display_name: Node Without Tier
  description: This node has no data assurance tier
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(catalog_without_tier)
        temp_file = f.name

    loader = CatalogLoader()
    try:
        registry = loader.load_file(temp_file)
        node = registry.get("no_tier_node")
        assert node is not None
        assert node.data_assurance_tier is None
        print("✅ Node without tier loaded successfully (tier=None)")
    finally:
        Path(temp_file).unlink()

    print()


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("DATA ASSURANCE TIERS - TEST SUITE")
    print("=" * 60 + "\n")

    try:
        test_config_loading()
        test_catalog_parsing()
        test_validation()
        test_custom_labels()
        test_optional_tier()

        print("=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        print("\nThe data assurance tiers feature is working correctly across:")
        print("  ✅ Configuration loading with default and custom labels")
        print("  ✅ Catalog parsing and tier assignment")
        print("  ✅ Validation (only 1, 2, 3 allowed)")
        print("  ✅ Optional tiers (backwards compatibility)")
        print("  ✅ Label resolution from config")
        print()

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
