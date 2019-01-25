#!/usr/bin/python3

from PIL import Image, ImageDraw
from sys import argv, stdout
import json
import numpy as np

class Space:
    """A space consists of an identifier, a (possibly empty) iterable
    sequence of references, and a number of flags.

    """

    def __init__(self, space, refs):
        """Constructs a space given a (possibly tagged) identifier and a
        sequence of references. If the tagged space identifier ends
        with a question mark, the space will be hidden and the
        identifier will not contain the question mark. If the
        identifier is the empty string, it defaults to "gap". If the
        identifier is "nil", it is translated to None.

        """
        self.space = space_abbr(space)
        self.refs = refs
        self.show = not space.endswith("?")

    def __str__(self):
        return "Space({!r}, {!r})".format(self.space, self.refs)

    def __repr__(self):
        return str(self)

    def image(self, spaces):
        """Looks up the image for the space, given the configuration
        information, and returns a Pillow image object. The argument
        should be the image containing all of the spaces. The global
        configuration dictionary will be used to determine which part
        of the image to crop out. If the space identifier is None or
        the space is hidden, None is returned.

        """
        if self.space is None or not self.show:
            return None
        coords = dictionary['spaces'][self.space]['coords']
        x, y, w, h = tuple(map(int, coords.split(",")))
        return spaces.crop((x, y, w, h))

    def layer(self):
        """Returns the layer of this space. The layer of a space is 0 if it is
        a gap and 1 otherwise.

        """
        return space_layer(self.space)

class Ref:
    """References are stored for items and tokens in the game. A reference
    consists of an identifier, an item identifier (which might be
    "nil"), and a relative position within the space. If the item
    identifier is non-nil, then the full identifier should be "item".

    """

    def __init__(self, name, item, pos):
        self.name = name
        self.item = item
        self.pos = pos

    def __str__(self):
        return "Ref({!r}, {!r})".format(self.name, self.item, self.pos)

    def __repr__(self):
        return str(self)

    def _image(self, tokens, d, name):
        if name not in d:
            return None
        if 'thumbnail' not in d[name]:
            return None
        x, y = d[name]['thumbnail']
        spanx, spany = 1, 1
        if 'span' in d[name]:
            spanx, spany = d[name]['span']
        return tokens.crop((x, y, x + 16 * spanx, y + 16 * spany))

    def image(self, tokens):
        """Given the image of tokens, produces a cropped variant which
        consists only of the given token.

        """
        return self._image(tokens, dictionary['items'], self.item) or self._image(tokens, dictionary['tokens'], self.name)

with open("config.json") as main_file:
    config = json.load(main_file)
    with open(config['files']['dict']) as dict_file:
        dictionary = json.load(dict_file)

def spaces_png():
    """Opens the spaces image and returns it as a Pillow object."""
    return Image.open(config['files']['spaces'])

def tokens_png():
    """Opens the tokens image and returns it as a Pillow object."""
    return Image.open(config['files']['tokens'])

def space_abbr(space):
    """If the identifier ends with a ?, this function strips the question
    mark. If the identifier is "nil", it is translated to None. If the
    identifier is "", it is translated to "gap".

    """
    if space.endswith("?"):
        space = space[:-1]
    if space == "nil":
        return None
    elif space == "":
        return "gap"
    else:
        return space

def space_layer(space):
    """Returns the layer of the space. All non-gap, non-None spaces are in
    layer 1. Gaps always fall in layer 0. The None space has no layer,
    so this function will return None in that case.

    """
    if space is None:
        return None
    elif space == "gap":
        return 0
    else:
        return 1

WIDTH = 32
HEIGHT = 32

def highlight(image, args):
    draw = ImageDraw.Draw(image)
    rc, num = args
    num = int(num)
    if rc == 'ROW':
        x0, y0 = 0, HEIGHT * num
        x1, y1 = image.size[0], HEIGHT * (num + 1)
    elif rc == 'COLUMN':
        x0, y0 = WIDTH * num, 0
        x1, y1 = WIDTH * (num + 1), image.size[1]
    draw.line([(x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0)],
              fill='red',
              width=4)

DIRECTIVES = {
    "HIGHLIGHT": highlight
}

def load_table(fname):
    """Given a filename, loads the file as a table file containing the
    board spaces and references. A 3-tuple is returned, containing

    1. The numpy array representing the board.
    2. A dictionary of Ref objects, with the abbreviations as the keys.
    3. A list of directives.

    Spaces whose identifier contains a "*" will have the asterisk
    stripped, as the asterisk is primarily intended for the GM's
    notes.

    """

    with open(fname) as infile:
        while infile.readline().startswith("#"):
            pass # Ignore leading comments

        # Version
        version = int(infile.readline())
        if version != 1:
            raise StandardError("Invalid version " + str(version))

        # The board text
        headline = infile.readline()
        table = []
        width = headline.count("+") - 1
        while True:
            curr = []
            spaces_arr = infile.readline()
            if spaces_arr.strip() == "":
                break
            spaces_arr = map(str.strip, spaces_arr.split("|")[1:-1])
            tokens_arr = map(str.strip, infile.readline().split("|")[1:-1])
            for v, z in zip(spaces_arr, tokens_arr):
                v = v.replace("*", "")
                curr.append(Space(v, list(z)))
            table.append(curr)
            infile.readline() # The next header

        # Token references
        refs = {}
        while True:
            curr = infile.readline()
            if curr.strip() == "":
                break
            ref, name, item, x, y = curr.split()
            refs[ref] = Ref(name, item, (int(x), int(y)))

        # Directives
        dirs = []
        while True:
            curr = infile.readline()
            if curr.strip() == "":
                break
            data = curr.split()
            fn = DIRECTIVES[data[0]]
            dirs.append(lambda image: fn(image, data[1:]))

        return (np.array(table), refs, dirs)


def render_image(table, refs, dirs):
    """Given the output of load_table, renders the various layers as a
    Pillow image and returns the image object.

    """
    with spaces_png() as spaces, tokens_png() as tokens:

        # Instantiate the image
        height, width = table.shape
        result = Image.new("RGBA", (width * WIDTH, height * HEIGHT))

        # Gap layer
        for y, row in enumerate(table):
            for x, elem in enumerate(row):
                if elem.layer() == 0:
                    img = elem.image(spaces)
                    if img is not None:
                        result.paste(img, (x * WIDTH, y * HEIGHT), img)

        # Normal space layer
        for y, row in enumerate(table):
            for x, elem in enumerate(row):
                if elem.layer() == 1:
                    img = elem.image(spaces)
                    if img is not None:
                        result.paste(img, (x * WIDTH, y * HEIGHT), img)

        # Ref layer
        for y, row in enumerate(table):
            for x, elem in enumerate(row):
                for ref in elem.refs:
                    img = refs[ref].image(tokens)
                    dx, dy = refs[ref].pos
                    if img is not None:
                        result.paste(img, (x * WIDTH + dx, y * HEIGHT + dy), img)

        # Directives
        for d in dirs:
            d(result)

        return result

def render_json(table, refs):
    """Given the output of load_table, renders the JSON output necessary
    for compatibility with the interactive board.

    """
    # TODO Multi-spaces aren't handled here right now
    spaces = []
    tokens = []
    for y, row in enumerate(table):
        curr = []
        for x, elem in enumerate(row):
            curr.append(elem.space or "gap")
            for ref in elem.refs:
                name = refs[ref].name
                dx, dy = refs[ref].pos
                if name == "item":
                    name = refs[ref].item
                obj = {
                    'object': name,
                    'position': [x * WIDTH + dx, y * HEIGHT + dy]
                }
                tokens.append(obj)
        spaces.append(curr)
    data = {
        '0': {'spaces': spaces, 'tokens': tokens}
    }
    return data

if __name__ == "__main__":
    setting = argv[1]
    infile = argv[2]
    table, refs, dirs = load_table(infile)
    if setting == '-i':
        with render_image(table, refs, dirs) as img:
            if len(argv) > 3:
                img.save(argv[3])
            else:
                img.show()
    elif setting == '-t':
        data = render_json(table, refs)
        json.dump(data, stdout)
        print()
