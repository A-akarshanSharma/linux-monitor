from collections import namedtuple

import pytest

from app.collectors import disk

Partition = namedtuple("Partition", "device mountpoint fstype opts")
Usage = namedtuple("Usage", "total used free percent")

EXCLUDE = ["tmpfs", "squashfs", "overlay", "9p", "fuse.*"]


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    partitions: list[Partition],
    usages: dict[str, Usage | Exception],
) -> None:
    monkeypatch.setattr(disk.psutil, "disk_partitions", lambda all=False: partitions)

    def fake_usage(path: str) -> Usage:
        result = usages[path]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(disk.psutil, "disk_usage", fake_usage)


def _ext4(device: str, mount: str) -> Partition:
    return Partition(device, mount, "ext4", "rw")


def test_reports_real_filesystems_sorted_by_mountpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        [_ext4("/dev/sdb1", "/data"), _ext4("/dev/sda1", "/")],
        {"/": Usage(100, 40, 60, 40.0), "/data": Usage(200, 180, 20, 90.0)},
    )

    result = disk.collect_disks(EXCLUDE)

    assert [d.mountpoint for d in result] == ["/", "/data"]
    assert result[1].percent == 90.0
    assert result[1].used_bytes == 180


def test_pseudo_filesystems_are_excluded_including_wildcards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(
        monkeypatch,
        [
            _ext4("/dev/sda1", "/"),
            Partition("tmpfs", "/tmp", "tmpfs", "rw"),
            Partition("/dev/loop0", "/mnt/snapimg", "squashfs", "ro"),
            Partition("C:\\", "/mnt/c", "9p", "rw"),
            Partition("remote:/share", "/mnt/share", "fuse.sshfs", "rw"),
        ],
        {"/": Usage(100, 40, 60, 40.0)},
    )

    assert [d.mountpoint for d in disk.collect_disks(EXCLUDE)] == ["/"]


def test_fstype_matching_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        [_ext4("/dev/sda1", "/"), Partition("x", "/mnt/x", "TMPFS", "rw")],
        {"/": Usage(100, 40, 60, 40.0)},
    )

    assert [d.mountpoint for d in disk.collect_disks(["TmpFS"])] == ["/"]


@pytest.mark.parametrize(
    "mount", ["/snap/core/1", "/run/user/1000", "/sys/fs/x", "/var/lib/docker/vfs"]
)
def test_excluded_mount_prefixes(monkeypatch: pytest.MonkeyPatch, mount: str) -> None:
    _patch(monkeypatch, [_ext4("/dev/sdx", mount)], {mount: Usage(100, 100, 0, 100.0)})

    assert disk.collect_disks([]) == []


def test_prefix_match_respects_path_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    """/runtime must not be treated as a sub-path of /run."""
    _patch(monkeypatch, [_ext4("/dev/sdb1", "/runtime")], {"/runtime": Usage(100, 10, 90, 10.0)})

    assert [d.mountpoint for d in disk.collect_disks([])] == ["/runtime"]


def test_bind_mounts_of_same_device_are_reported_once(monkeypatch: pytest.MonkeyPatch) -> None:
    usage = Usage(100, 40, 60, 40.0)
    _patch(
        monkeypatch,
        [_ext4("/dev/sda1", "/etc/hosts"), _ext4("/dev/sda1", "/")],
        {"/": usage, "/etc/hosts": usage},
    )

    result = disk.collect_disks([])

    assert [d.mountpoint for d in result] == ["/"]  # shortest path wins


def test_unreadable_mount_is_skipped_not_fatal(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch(
        monkeypatch,
        [_ext4("/dev/sda1", "/"), _ext4("/dev/sdb1", "/secret")],
        {"/": Usage(100, 40, 60, 40.0), "/secret": PermissionError("denied")},
    )

    with caplog.at_level("WARNING"):
        result = disk.collect_disks([])

    assert [d.mountpoint for d in result] == ["/"]
    assert any(r.message == "disk_usage_unavailable" for r in caplog.records)


def test_zero_size_filesystems_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, [_ext4("/dev/sda1", "/")], {"/": Usage(0, 0, 0, 0.0)})

    assert disk.collect_disks([]) == []
