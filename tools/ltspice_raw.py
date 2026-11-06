"""Read an LTspice binary .raw transient file (stdlib only): time + traces, per .step run.

    python -I tools/ltspice_raw.py <file.raw> [trace ...]   # prints variables, steps, and min/max per trace

Format: UTF-16-LE header ending in 'Binary:\n'; points of float64 time + float32 per variable. Stepped runs are
concatenated: a run starts where time goes back to its start value. Compressed raws work (points are as stored).
"""
import array
import pathlib
import sys

HEADER_END = 'Binary:\n'
ENCODING = 'utf-16-le'
TIME_BYTES, VALUE_BYTES = 8, 4


def read(path):
    """{'vars': [names], 'steps': [{'time': [...], name: [...]}]}."""
    data = pathlib.Path(path).read_bytes()
    marker = HEADER_END.encode(ENCODING)
    end = data.index(marker) + len(marker)
    header = data[:end].decode(ENCODING)
    lines = header.splitlines()
    npoints = int(next(l for l in lines if l.startswith('No. Points:')).split(':')[1])
    nvars = int(next(l for l in lines if l.startswith('No. Variables:')).split(':')[1])
    vstart = lines.index('Variables:') + 1
    names = [lines[vstart + i].split('\t')[2] for i in range(nvars)]
    rec = TIME_BYTES + VALUE_BYTES * (nvars - 1)
    body = memoryview(data)[end:end + rec * npoints]
    time, cols = [], [[] for _ in range(nvars - 1)]
    for k in range(npoints):
        off = k * rec
        time.append(abs(array.array('d', bytes(body[off:off + TIME_BYTES]))[0]))
        vals = array.array('f', bytes(body[off + TIME_BYTES:off + rec]))
        for c, v in zip(cols, vals):
            c.append(v)
    steps, start = [], 0
    for k in range(1, npoints + 1):
        if k == npoints or time[k] < time[k - 1]:
            st = {'time': time[start:k]}
            for n, c in zip(names[1:], cols):
                st[n] = c[start:k]
            steps.append(st)
            start = k
    return {'vars': names, 'steps': steps}


def main(argv):
    r = read(argv[1])
    print('variables:', ' '.join(r['vars']))
    print('steps:', len(r['steps']))
    for i, st in enumerate(r['steps']):
        for name in argv[2:]:
            v = st[name]
            print(f'step {i + 1} {name}: min {min(v):.4g} max {max(v):.4g}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
