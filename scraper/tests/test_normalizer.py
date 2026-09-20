from app.services.normalizer import normalize_title
def test_op():
 assert normalize_title('One Piece OP-08 Display Japanese')['language']=='JP'
