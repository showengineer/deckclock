from construct import Struct, Int8ul, Int16ul, Int32ul, OneOf, IfThenElse, Padding, Tell, this
from .piostring import OffsetPioString

ALBUM_ENTRY_MAGIC = 0x80
LONG_ALBUM_ENTRY_MAGIC = 0x84

Album = Struct(
  "entry_start" / Tell,
  "magic" / OneOf(Int16ul, [ALBUM_ENTRY_MAGIC, LONG_ALBUM_ENTRY_MAGIC]),
  "index_shift" / Int16ul,
  Padding(4),
  "album_artist_id" / Int32ul,
  "id" / Int32ul,
  Padding(4),
  "unknown" / IfThenElse(this.magic == LONG_ALBUM_ENTRY_MAGIC, Int16ul, Int8ul),
  "name_idx" / IfThenElse(this.magic == LONG_ALBUM_ENTRY_MAGIC, Int16ul, Int8ul),
  "name" / OffsetPioString(this.name_idx)
)
