"""Tests for FileTracker."""

from isotope_core.context import FileTracker


class TestFileTrackerRecordRead:
    """Tests for record_read."""

    def test_record_read_adds_to_files_read(self) -> None:
        tracker = FileTracker()
        tracker.record_read("/tmp/foo.py")
        assert "/tmp/foo.py" in tracker.files_read

    def test_record_read_multiple_files(self) -> None:
        tracker = FileTracker()
        tracker.record_read("/tmp/a.py")
        tracker.record_read("/tmp/b.py")
        assert tracker.files_read == {"/tmp/a.py", "/tmp/b.py"}

    def test_record_read_does_not_affect_files_modified(self) -> None:
        tracker = FileTracker()
        tracker.record_read("/tmp/foo.py")
        assert len(tracker.files_modified) == 0


class TestFileTrackerRecordWrite:
    """Tests for record_write."""

    def test_record_write_adds_to_files_modified(self) -> None:
        tracker = FileTracker()
        tracker.record_write("/tmp/foo.py")
        assert "/tmp/foo.py" in tracker.files_modified

    def test_record_write_does_not_affect_files_read(self) -> None:
        tracker = FileTracker()
        tracker.record_write("/tmp/foo.py")
        assert len(tracker.files_read) == 0


class TestFileTrackerRecordEdit:
    """Tests for record_edit."""

    def test_record_edit_adds_to_files_modified(self) -> None:
        tracker = FileTracker()
        tracker.record_edit("/tmp/bar.py")
        assert "/tmp/bar.py" in tracker.files_modified

    def test_record_edit_does_not_affect_files_read(self) -> None:
        tracker = FileTracker()
        tracker.record_edit("/tmp/bar.py")
        assert len(tracker.files_read) == 0


class TestFileTrackerSnapshot:
    """Tests for snapshot."""

    def test_snapshot_returns_sorted_lists(self) -> None:
        tracker = FileTracker()
        tracker.record_read("/tmp/z.py")
        tracker.record_read("/tmp/a.py")
        tracker.record_write("/tmp/m.py")
        tracker.record_edit("/tmp/b.py")

        result = tracker.snapshot()

        assert result == {
            "files_read": ["/tmp/a.py", "/tmp/z.py"],
            "files_modified": ["/tmp/b.py", "/tmp/m.py"],
        }

    def test_snapshot_empty_tracker(self) -> None:
        tracker = FileTracker()
        result = tracker.snapshot()
        assert result == {"files_read": [], "files_modified": []}

    def test_snapshot_returns_new_lists(self) -> None:
        """Snapshot should return fresh lists, not references to internal state."""
        tracker = FileTracker()
        tracker.record_read("/tmp/a.py")
        snap1 = tracker.snapshot()
        tracker.record_read("/tmp/b.py")
        snap2 = tracker.snapshot()
        assert snap1 != snap2


class TestFileTrackerReset:
    """Tests for reset."""

    def test_reset_clears_both_sets(self) -> None:
        tracker = FileTracker()
        tracker.record_read("/tmp/a.py")
        tracker.record_write("/tmp/b.py")
        tracker.record_edit("/tmp/c.py")

        tracker.reset()

        assert len(tracker.files_read) == 0
        assert len(tracker.files_modified) == 0

    def test_reset_allows_reuse(self) -> None:
        tracker = FileTracker()
        tracker.record_read("/tmp/a.py")
        tracker.reset()
        tracker.record_read("/tmp/b.py")
        assert tracker.files_read == {"/tmp/b.py"}


class TestFileTrackerDuplicates:
    """Tests that duplicate paths don't create duplicates (sets)."""

    def test_duplicate_read_paths(self) -> None:
        tracker = FileTracker()
        tracker.record_read("/tmp/foo.py")
        tracker.record_read("/tmp/foo.py")
        tracker.record_read("/tmp/foo.py")
        assert tracker.files_read == {"/tmp/foo.py"}

    def test_duplicate_write_paths(self) -> None:
        tracker = FileTracker()
        tracker.record_write("/tmp/bar.py")
        tracker.record_write("/tmp/bar.py")
        assert tracker.files_modified == {"/tmp/bar.py"}

    def test_duplicate_edit_paths(self) -> None:
        tracker = FileTracker()
        tracker.record_edit("/tmp/baz.py")
        tracker.record_edit("/tmp/baz.py")
        assert tracker.files_modified == {"/tmp/baz.py"}

    def test_write_and_edit_same_path(self) -> None:
        tracker = FileTracker()
        tracker.record_write("/tmp/foo.py")
        tracker.record_edit("/tmp/foo.py")
        assert tracker.files_modified == {"/tmp/foo.py"}
