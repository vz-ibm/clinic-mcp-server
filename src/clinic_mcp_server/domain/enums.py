from enum import Enum, StrEnum


class MembershipType(StrEnum):
    REGULAR = "regular"
    SILVER = "silver"
    GOLD = "gold"


class CardBrand(str, Enum):
    visa = "visa"
    mastercard = "mastercard"
    amex = "amex"
    discover = "discover"
    diners = "diners"
    jcb = "jcb"
    unionpay = "unionpay"
    other = "other"
