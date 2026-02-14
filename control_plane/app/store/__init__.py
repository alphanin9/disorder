from control_plane.app.store.minio import MinioBlobStore


_blob_store: MinioBlobStore | None = None


def get_blob_store() -> MinioBlobStore:
    global _blob_store
    if _blob_store is None:
        _blob_store = MinioBlobStore()
    return _blob_store
