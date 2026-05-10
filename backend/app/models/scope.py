from typing import Literal

# A scope partitions accounts and category groups into independent budget
# pools that share one user, one app, and one screen — but have separate
# Ready-to-Assign totals. "personal" is the user's own money; "shared" is
# money in a joint account managed jointly with someone outside the app.
SCOPES: tuple[str, ...] = ("personal", "shared")
PERSONAL: str = "personal"
SHARED: str = "shared"

Scope = Literal["personal", "shared"]
