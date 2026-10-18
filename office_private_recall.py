"""公開版不讀取辦公室以外的私人聊天或記憶索引。"""
import logging
LOG=logging.getLogger(__name__)
NOTICE='公開版不會自動搜尋私人聊天；需要的資料請由本人明確提供。'
def lookup(worker,title,brief,*,jobs_root,excluded_session_ids=(),cross_team=False):
    return []
