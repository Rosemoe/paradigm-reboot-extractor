import numpy as np
import struct
import json
import zipfile
import base64
import os
import sys
import getopt
from fsb5 import FSB5
from Crypto.Cipher import AES
from UnityPy import Environment
from UnityPy.enums import ClassIDType
from UnityPy.classes import (
    TextAsset,
    AudioClip,
    Sprite,
    Texture2D
)


RESOURCE_KEY = bytes([167,60,197,249,11,195,33,178,81,117,106,147,183,10,147,56])


def get_resource_iv(filename: str) -> bytes:
    with np.errstate(over='ignore'):
        data1 = np.int64(0x5B48FC7)
        for i in range(len(filename)):
            data1 = data1 * np.int64(31) + np.int64(ord(filename[i]))
        data2 = np.int64(0x12936E5)
        for i in range(len(filename) - 1, -1, -1):
            data2 = data2 * np.int64(31) + np.int64(ord(filename[i]))
        return data1.tobytes() + data2.tobytes()


def decrypt_resource_file(data: bytes, filename: str) -> bytes:
    aes = AES.new(RESOURCE_KEY, AES.MODE_CBC, iv=get_resource_iv(filename))
    return aes.decrypt(data)


Vector3IntSchema = [
    ('X', int),
    ('Y', int),
    ('Z', int)
]


CoverDisplayParamsSchema = [
    ('offsetX', float),
    ('offsetY', float),
    ('scale', float)
]


DifficultyLockSchema = [
    ('lockedDifficulty', int), # EnumType: ParadigmHelper.EDifficulty
    ('unlockDifficultyRequirementType', int), # EnumType: SongMeta.UnlockDifficultyRequirementType
    ('unlockDifficultyRequirementParams', str, True)
]


SongMetaChartSchema = [
    ('difficulty', int), # EnumType: ParadigmHelper.EDifficulty
    ('level', int),
    ('isPlus', bool),
    ('noter', str),
    ('overrideMusicAddress', str),
] + ([('unused', 'byte')] * 12) # Type Sprite, skipped


SongMetaItemSchema = [
    ('title', str),
    ('bpm', str),
    ('genre', str),
    ('address', str),
    ('musician', str),
    ('illustrator', str),
    ('comment', str),
    ('copyright', str),
    ('isOriginal', bool),
    ('isVersionOriginal', bool),
    ('isNewlyUpdated', bool),
    ('updateVersion', Vector3IntSchema),
    ('charts', SongMetaChartSchema, True),
    ('coverDisplayParams', CoverDisplayParamsSchema),
    ('trackType', int), # EnumType: TrackType
    ('typeParams', str, True),
    ('fromProductType', int), # EnumType: OnlineStoreProductData.ProductEnum
    ('fromFreeDataSingleAlbum', int), # EnumType: SongMeta.FreeDataSingleAlbumEnum
    ('difficultyLockList', DifficultyLockSchema, True),
    ('isHiddenExceptOwn', bool)
]


class ByteReader:
    def __init__(self, data: bytes):
        self.data = data
        self.position = 0
        self.type_readers = {
            int: self.read_int,
            str: self.read_string,
            bool: self.read_bool,
            float: self.read_float,
            'byte': self.read_byte
        }
        
    def read_bool(self) -> bool:
        return self.read_int() != 0
    
    def read_byte(self) -> int:
        self.position += 1
        return self.data[self.position - 1]

    def read_int(self) -> int:
        self.position += 4
        return struct.unpack("i", self.data[self.position - 4:self.position])[0]

    def read_float(self) -> float:
        self.position += 4
        return struct.unpack("f", self.data[self.position - 4:self.position])[0]

    def read_string(self) -> str:
        length = self.read_int()
        result = self.data[self.position:self.position + length].decode()
        self.position += length // 4 * 4
        if length % 4 != 0:
            self.position += 4
        return result

    def read_schema(self, schema: list, array=False):
        if array:
            count = self.read_int()
            items = []
            for _ in range(count):
                items.append(self.read_schema(schema))
            return items
        result = {}
        for item in schema:
            if isinstance(item[1], list):
                v = self.read_schema(item[1], len(item) >= 3 and item[2])
            elif len(item) >= 3 and item[2]:
                reader = self.type_readers[item[1]]
                v = [reader() for _ in range(self.read_int())]
            else:
                reader = self.type_readers[item[1]]
                v = reader()
            if item[0] != 'unused':
                result[item[0]] = v
        return result


def extract_song_meta(apk_path: str):
    print('Exporting song metadata. Metadata will be exported to ./song-meta.json')
    env = Environment()
    with open(apk_path, 'rb') as f:
        env.load_file(f)
    for obj in env.objects:
        if obj.type.name != 'MonoBehaviour':
            continue
        data = obj.read()
        script = data.m_Script.get_obj()
        if script and script.read().name == 'SongMeta':
            meta_data = data.raw_data.tobytes()[4:]
            rd = ByteReader(meta_data)
            result = rd.read_schema(SongMetaItemSchema, True)
            addr_set = set(x['address'] for x in result)
            if len(addr_set) < len(result):
                # Discard this one
                continue
            with open('song-meta.json', 'w', encoding='utf-8') as f:
                f.write(json.dumps(result, indent=2, ensure_ascii=False))
            print('Exported song metadata')
            return
    print('Failed to find SongMeta MonoBehavior data from loaded base apk')


def build_res_table(apk: zipfile.ZipFile):
    with apk.open("assets/aa/catalog.json") as f:
        data = json.load(f)
    
    key = base64.b64decode(data["m_KeyDataString"])
    bucket = base64.b64decode(data["m_BucketDataString"])
    entry = base64.b64decode(data["m_EntryDataString"])
    
    table = []
    reader = ByteReader(bucket)
    for _ in range(reader.read_int()):
        key_position = reader.read_int()
        key_type = key[key_position]
        key_position += 1
        if key_type == 0:
            length = key[key_position]
            key_position += 4
            key_value = key[key_position:key_position + length].decode()
        elif key_type == 1:
            length = key[key_position]
            key_position += 4
            key_value = key[key_position:key_position + length].decode("utf16")
        elif key_type == 4:
            key_value = key[key_position]
        else:
            raise BaseException(key_position, key_type)
        for i in range(reader.read_int()):
            entry_position = reader.read_int()
            entry_value = entry[4 + 28 * entry_position:4 + 28 * entry_position + 28]
            entry_value = entry_value[8] ^ entry_value[9] << 8
        table.append([key_value, entry_value])
    for i in range(len(table)):
        if table[i][1] != 65535:
            table[i][1] = table[table[i][1]][0]
    return table


def extract_songs(apk: zipfile.ZipFile, table):
    print('Exporting song resources. Songs will be exported to ./songs')
    env = Environment()
    for key, entry in table:
        if type(key) == str and type(entry) == str and key.startswith('s/'):
            file_decrypted = decrypt_resource_file(apk.read("assets/aa/Android/%s" % entry), entry[entry.rfind('/')+1:])
            env.load_file(file_decrypted, name=key)
    for k, entry in env.files.items():
        print('Exporting song resources:', k.removeprefix('s/'))
        obj = next(entry.get_filtered_objects([ClassIDType.TextAsset, ClassIDType.Sprite, ClassIDType.AudioClip])).read()
        k = 'songs/' + k.removeprefix('s/')
        addr = k[:k.rfind('/')]
        if not os.path.exists('./{}'.format(addr)):
            os.makedirs('./{}'.format(addr))
        if isinstance(obj, TextAsset):
            with open('./{}.txt'.format(k), 'wb') as f:
                f.write(bytes(obj.script))
        elif isinstance(obj, Sprite) or isinstance(obj, Texture2D):
            with open('./{}.png'.format(k), 'wb') as f:
                obj.image.save(f, format='PNG')
        elif isinstance(obj, AudioClip):
            fsb = FSB5(obj.m_AudioData)
            rebuilt_sample = fsb.rebuild_sample(fsb.samples[0])
            with open('./{}.ogg'.format(k), 'wb') as f:
                f.write(rebuilt_sample)


def extract_skins(apk: zipfile.ZipFile, table):
    print('Exporting skins. Skins will be exported to ./skins')
    env = Environment()
    for key, entry in table:
        if type(key) == str and type(entry) == str and 'Skin/' in key:
            file_decrypted = decrypt_resource_file(apk.read("assets/aa/Android/%s" % entry), entry[entry.rfind('/')+1:])
            env.load_file(file_decrypted, name=key)
    for k, entry in env.files.items():
        res_name = k[k.rfind('/')+1:]
        print('Exporting skin resources:', res_name)
        for obj in entry.get_objects():
            obj = obj.read()
            k = obj.name
            if not os.path.exists('./skins/{}'.format(res_name)):
                os.makedirs('./skins/{}'.format(res_name))
            if isinstance(obj, Sprite) or isinstance(obj, Texture2D):
                with open('./skins/{}/{}.png'.format(res_name, k), 'wb') as f:
                    obj.image.save(f, format='PNG')


HELP = '''Usage: extractor.py -i <apk_path> [-a <assets_apk_path>] [-h] [--songs] [--skins]
Options:
-i <apk_path>           Specify the input (base) apk file path
-a <assets_apk_path>    Specify additional assets apk file path
--songs                 Export song resources
--skins                 Export skin resources
-h                      Show this help'''


def main(args):
    try:
        opts, args = getopt.getopt(args, 'hi:a:', ['songs', 'skins'])
    except getopt.GetoptError:
        print('Invalid options', HELP, sep='\n')
        sys.exit(1)

    base_apk_path, assets_apk_path = None, None
    export_songs = False
    export_skins = False
    for opt, arg in opts:
        if opt == '-i':
            if base_apk_path:
                print('You may only specify one base apk path')
                sys.exit(1)
            base_apk_path = arg
        elif opt == '-h':
            print(HELP)
            sys.exit()
        elif opt == '-a':
            if assets_apk_path:
                print('You may only specify one assets apk path')
                sys.exit(1)
            assets_apk_path = arg
        elif opt == '--songs':
            export_songs = True
        elif opt == '--skins':
            export_skins = True

    if not base_apk_path:
        print('Must specify input (base) apk path.', HELP, sep='\n')
        sys.exit(1)

    extract_song_meta(base_apk_path)

    if not (export_songs or export_skins):
        return

    with zipfile.ZipFile(assets_apk_path if assets_apk_path else base_apk_path) as apk:
        print('Locating resources')
        try:
            table = build_res_table(apk)
        except:
            print('Failed to locate resources.')
            if not assets_apk_path:
                print('Hint: you may need to provide assets apk path')
            sys.exit(1)
        if export_songs:
            extract_songs(apk, table)
        if export_skins:
            extract_skins(apk, table)


if __name__ == '__main__':
    main(sys.argv[1:])
