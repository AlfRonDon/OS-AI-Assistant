from tools.emb.embeddings_stub import embed_texts


def test_embedding_length_and_type():
    vecs = embed_texts(["hello", "world"], dim=24)
    assert len(vecs) == 2
    assert all(len(v) == 24 for v in vecs)
    assert all(isinstance(x, float) for v in vecs for x in v)


def test_embedding_determinism():
    first = embed_texts(["repeat-me"], dim=16)[0]
    second = embed_texts(["repeat-me"], dim=16)[0]
    assert first == second
