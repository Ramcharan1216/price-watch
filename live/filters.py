"""What is NOT a new phone: accessories and used or refurbished items.
Shared by the price source and the catalog discovery so both agree."""
import re

ACCESSORY = re.compile(r"\b(case|cover|protector|tempered glass|screen guard|charger|adapter|cable|stand|holder|strap|"
                       r"skin|pouch|sleeve|tripod|stylus|earbuds|headphones|earphones|power ?bank|battery|mount|film)\b", re.I)
SECONDHAND = re.compile(r"\b(refurbished|renewed|used|pre-?owned|second ?hand|open box|like new)\b", re.I)


def is_accessory(title, query=""):
    """True for 'Samsung Galaxy S26 back cover'. Not applied to a word the user searched for on purpose."""
    return any(m.group(1).lower() not in query.lower() for m in ACCESSORY.finditer(title))


def is_secondhand(title, query=""):
    return any(m.group(1).lower() not in query.lower() for m in SECONDHAND.finditer(title))
