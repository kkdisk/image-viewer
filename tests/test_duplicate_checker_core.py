import pytest
from pathlib import Path
from PIL import Image
import os
import imagehash

from image_viewer.duplicate_checker.core.utils import format_size
from image_viewer.duplicate_checker.core.hasher import ImageHasher, ImageInfo
from image_viewer.duplicate_checker.core.comparator import ImageComparator, DuplicateGroup

# --- utils.py ---

def test_format_size():
    assert format_size(0) == "0 B"
    assert format_size(500) == "500.0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
    assert format_size(1024 * 1024 * 1024) == "1.0 GB"
    assert format_size(1024 * 1024 * 1024 * 1024) == "1.0 TB"

# --- hasher.py ---

class TestImageHasher:
    @pytest.fixture
    def hasher(self):
        return ImageHasher(algorithm="phash")

    def test_compute_file_hash(self, tmp_path, hasher):
        img_path = tmp_path / "test.png"
        Image.new("RGB", (10, 10), color="red").save(img_path)
        
        h1 = hasher.compute_file_hash(img_path)
        assert len(h1) == 32  # MD5 length
        
        # Same content should have same hash
        img_path2 = tmp_path / "test2.png"
        Image.new("RGB", (10, 10), color="red").save(img_path2)
        h2 = hasher.compute_file_hash(img_path2)
        assert h1 == h2

    def test_compute_perceptual_hash(self, tmp_path, hasher):
        img_path = tmp_path / "test.png"
        Image.new("RGB", (100, 100), color="red").save(img_path)
        
        phash = hasher.compute_perceptual_hash(img_path)
        assert isinstance(phash, imagehash.ImageHash)

# --- comparator.py ---

class TestDuplicateGroup:
    def test_stats(self, tmp_path):
        # Mock ImageInfo objects
        p1 = tmp_path / "img1.png"
        p2 = tmp_path / "img2.png"
        Image.new("RGB", (100, 100)).save(p1)
        Image.new("RGB", (50, 50)).save(p2)
        
        info1 = ImageInfo(p1) # ~100x100
        info2 = ImageInfo(p2) # ~50x50
        
        group = DuplicateGroup(group_id=1, images=[info1, info2])
        
        assert group.file_count == 2
        assert group.total_size == info1.file_size + info2.file_size
        # saveable_size should be the size of the smaller one
        assert group.saveable_size == min(info1.file_size, info2.file_size)
        
        best = group.get_best_image()
        assert best.filepath == p1  # Larger dimensions

class TestImageComparator:
    def test_find_exact_duplicates(self, tmp_path):
        p1 = tmp_path / "img1.png"
        p2 = tmp_path / "img2.png"
        p3 = tmp_path / "img3.png"
        
        img_data = Image.new("RGB", (10, 10), color="blue")
        img_data.save(p1)
        img_data.save(p2) # Duplicate of p1
        Image.new("RGB", (10, 10), color="red").save(p3) # Different
        
        comparator = ImageComparator(mode="exact")
        comparator.process_files([p1, p2, p3])
        groups = comparator.find_duplicates()
        
        assert len(groups) == 1
        assert groups[0].file_count == 2
        assert groups[0].match_type == "exact"

    def test_find_similar_duplicates(self, tmp_path):
        p1 = tmp_path / "img1.png"
        p2 = tmp_path / "img2.png"
        
        # Create very similar images
        Image.new("RGB", (100, 100), color=(255, 0, 0)).save(p1)
        # Slightly different red
        Image.new("RGB", (100, 100), color=(250, 2, 2)).save(p2)
        
        comparator = ImageComparator(mode="similar", threshold=5)
        comparator.process_files([p1, p2])
        groups = comparator.find_duplicates()
        
        assert len(groups) == 1
        assert groups[0].match_type == "similar"
