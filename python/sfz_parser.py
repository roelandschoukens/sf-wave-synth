
# parser tokens
import dataclasses
import re


class ParseError(Exception):
    pass


@dataclasses.dataclass
class Header:
    name : str

    def __str__(self):
        return f"<{self.name}>"

@dataclasses.dataclass
class Instr:
    opcode : str
    value : str

    def __str__(self):
        return f"{self.opcode}={self.value}"

@dataclasses.dataclass
class End:
    pass


PAT_HEADER = re.compile(r'<(\w+)>\s*')
PAT_OPCODE = re.compile(r'(\w+)=(\S+)\s*')


def sfz_tokens(file):
    """ Tokenize an SFZ file
     
    This does not retain comments and whitespace, it only yields the headers
    and instructions. At the end of file one End token is yielded. """
    for line_nr, line in enumerate(file, start=1):
        line = re.sub(r"//.*", "", line) # eat comments
        line = line.strip()
        offset = 0
        # while still characters left:
        while offset < len(line):
            # every regex also eats trailing whitespace
            if (m := PAT_HEADER.match(line, offset)):
                yield Header(m[1])
                offset += len(m[0])
            elif (m := PAT_OPCODE.match(line, offset)):
                yield Instr(m[1], m[2])
                offset += len(m[0])
            else:
                raise ParseError(f"Syntax error on line {line_nr} around {line[offset:offset+20]}")
    yield End()

