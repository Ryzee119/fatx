from .libfatxfs import ffi
from .libfatxfs.lib import *
import os


class FatxAttr:

	def __init__(self, filename, attributes, filesize):
		self.filename = filename
		self.attributes = attributes
		self.file_size = filesize

	@property
	def is_readonly(self): return self.attributes & (1<<0)

	@property
	def is_system(self): return self.attributes & (1<<1)

	@property
	def is_hidden(self): return self.attributes & (1<<2)

	@property
	def is_volume(self): return self.attributes & (1<<3)

	@property
	def is_directory(self): return self.attributes & (1<<4)

	@property
	def is_file(self): return not self.is_directory

	def __repr__(self):
		attr_desc = ','.join(
			  ['dir'  if self.is_directory else 'file']
			+ ['ro']  if self.is_readonly else []
			+ ['sys'] if self.is_system   else []
			+ ['hid'] if self.is_hidden   else []
			+ ['vol'] if self.is_volume   else []
			)
		return f'<FatxAttr name={self.filename} attr={attr_desc} size={self.file_size:#x}>'


class Fatx:

	def __init__(self, path, offset=None, size=None, drive='c', secsize=512):
		self.fs = pyfatx_open_helper()
		assert self.fs
		if offset is None:
			partitions = {
				'x': (0x00080000, 0x02ee00000),
				'y': (0x2ee80000, 0x02ee00000),
				'z': (0x5dc80000, 0x02ee00000),
				'c': (0x8ca80000, 0x01f400000),
				'e': (0xabe80000, 0x131f00000),
			}
			offset, size = partitions[drive]
		if isinstance(path, str):
			path = path.encode('utf-8')
		s = fatx_open_device(self.fs, path, offset, size, secsize)
		assert s == 0

	def _sanitize_path(self, path):
		if isinstance(path, str):
			path = path.encode('utf-8')
		if not path.startswith(b'/'):
			path = b'/' + path
		return path

	def _create_attr(self, in_attr):
		fname = ffi.string(in_attr.filename).decode('ascii')
		return FatxAttr(fname, in_attr.attributes, in_attr.file_size)

	def get_attr(self, path):
		path = self._sanitize_path(path)
		attr = ffi.new('struct fatx_attr *')
		s = fatx_get_attr(self.fs, path, attr)
		assert s == 0
		return self._create_attr(attr)

	def listdir(self, path):
		path = self._sanitize_path(path)
		d = ffi.new('struct fatx_dir *')
		s = fatx_open_dir(self.fs, path, d)
		assert s == 0

		dirent = ffi.new('struct fatx_dirent *')
		attr = ffi.new('struct fatx_attr *')
		next_dirent = ffi.new('struct fatx_dirent **')

		while True:
			s = fatx_read_dir(self.fs, d, dirent, attr, next_dirent)
			if s != 0:
				break

			yield self._create_attr(attr)

			s = fatx_next_dir_entry(self.fs, d)
			if s != 0:
				break

		s = fatx_close_dir(self.fs, d)
		assert s == 0

	def walk(self, path):
		attrs = list(self.listdir(path))
		dirnames = [d.filename for d in attrs if d.is_directory]
		filenames = [f.filename for f in attrs if f.is_file]
		yield (path, dirnames, filenames)
		for d in dirnames:
			yield from self.walk(os.path.join(path, d))

	def read(self, path, offset=0, size=None):
		path = self._sanitize_path(path)
		attr = self.get_attr(path)
		assert(attr.is_file)
		assert(offset < attr.file_size)
		if size is None:
			size = attr.file_size - offset
		if size == 0:
			return b''
		buf = ffi.new(f'char[{attr.file_size}]')
		s = fatx_read(self.fs, path, offset, size, buf)
		assert s == size
		return ffi.buffer(buf)