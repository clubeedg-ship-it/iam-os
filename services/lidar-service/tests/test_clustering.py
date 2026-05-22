"""Tests for the flood-fill point clustering used in touch detection."""

from iam_lidar.detection.clustering import cluster_points


def test_no_points_yields_no_clusters():
    assert cluster_points([], tolerance_mm=100.0) == []


def test_single_point_is_one_cluster():
    clusters = cluster_points([(0.0, 0.0)], tolerance_mm=100.0)
    assert len(clusters) == 1
    assert clusters[0] == [(0.0, 0.0)]


def test_points_within_tolerance_join_one_cluster():
    clusters = cluster_points([(0.0, 0.0), (50.0, 0.0)], tolerance_mm=100.0)
    assert len(clusters) == 1
    assert len(clusters[0]) == 2


def test_points_beyond_tolerance_form_separate_clusters():
    clusters = cluster_points([(0.0, 0.0), (500.0, 0.0)], tolerance_mm=100.0)
    assert len(clusters) == 2


def test_clustering_is_transitive_along_a_chain():
    # Each consecutive pair is within tolerance; the chain itself spans
    # more than the tolerance, so only flood-fill keeps it as one cluster.
    points = [(0.0, 0.0), (80.0, 0.0), (160.0, 0.0), (240.0, 0.0)]
    clusters = cluster_points(points, tolerance_mm=100.0)
    assert len(clusters) == 1
    assert len(clusters[0]) == 4


def test_two_separate_groups_are_two_clusters():
    points = [(0.0, 0.0), (30.0, 0.0), (1000.0, 1000.0), (1030.0, 1000.0)]
    clusters = cluster_points(points, tolerance_mm=100.0)
    assert len(clusters) == 2
    assert sorted(len(c) for c in clusters) == [2, 2]
