from construct import Bytes, Computed, ExprAdapter, FocusedSeq, Int8ul, Int16ul, Int24ul, Padding, Pointer, PaddedString, Restreamed, Switch, this

def utf16_pio_length(ctx):
  length = ctx.declared_length - 4
  if length < 2:
    return max(length, 0)
  stream = ctx._io
  position = stream.tell()
  stream.seek(length - 2, 1)
  last_code_unit = stream.read(2)
  stream.seek(position)
  if len(last_code_unit) == 2 and 0xd800 <= int.from_bytes(last_code_unit, "big") <= 0xdbff:
    length += 2
  return length

PioString = FocusedSeq("data",
  "padded_length" / Int8ul,
  "data" / Switch(this.padded_length, {
    # string longer than 127 bytes, prefixed with 3 bytes length
    0x40: FocusedSeq("text",
      "actual_length" / ExprAdapter(Int16ul, lambda o,c: o-4, lambda o,c: o+4),
      Padding(1),
      "text" / PaddedString(this.actual_length, encoding="ascii")),
    # utf-16 text
    0x90: FocusedSeq("text",
      "declared_length" / Int16ul,
      "actual_length" / Computed(utf16_pio_length),
      "text" / PaddedString(this.actual_length, "utf-16-be")),
  }, default= # just ascii text
    FocusedSeq("text",
     "actual_length" / Computed((this._.padded_length-1)//2-1),
      "text" / PaddedString(this.actual_length, encoding="ascii"))
))

# parses a PioString relative to entry start using an str_idx array
def OffsetPioString(index):
  return Pointer(this.entry_start+index, PioString)

# parses a PioString relative to entry start using an str_idx array
def IndexedPioString(index):
  return Pointer(this.entry_start+this.str_idx[index], PioString)
