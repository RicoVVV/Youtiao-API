"""钱包数据访问层，集中钱包和账本的数据库操作。"""

from app.modules.wallet.crud.wallet_crud import WalletCrud

__all__ = ["WalletCrud"]
