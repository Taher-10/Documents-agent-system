import os

# Hash modulus for BM25 sparse index mapping.
# Tokens are mapped to integer indices via hashlib.md5(token) % SPARSE_DIM.
# Changing this value invalidates all stored sparse indices — the sentinel
# guard in VectorStoreManager will raise RuntimeError on mismatch.
SPARSE_DIM: int = int(os.getenv("SPARSE_DIM", str(2 ** 17)))  # 131072
