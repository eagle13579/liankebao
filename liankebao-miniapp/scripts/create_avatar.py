import struct, zlib

def create_gray_png(width=10, height=10):
    raw_data = b''
    for y in range(height):
        raw_data += b'\x00'
        for x in range(width):
            raw_data += b'\x9e\x9e\x9e\xff'
    compressed = zlib.compress(raw_data)

    def make_chunk(chunk_type, data):
        chunk = chunk_type + data
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', zlib.crc32(chunk) & 0xffffffff)

    png = b'\x89PNG\r\n\x1a\n'
    png += make_chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    png += make_chunk(b'IDAT', compressed)
    png += make_chunk(b'IEND', b'')
    return png

png_data = create_gray_png()
with open('/mnt/d/chainke-full/liankebao-miniapp/images/default-avatar.png', 'wb') as f:
    f.write(png_data)

import os
size = os.path.getsize('/mnt/d/chainke-full/liankebao-miniapp/images/default-avatar.png')
print(f'OK - created {size}B')
