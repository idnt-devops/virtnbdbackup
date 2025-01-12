"""
Sparsestream format description
"""
import json
import os
import datetime

from libvirtnbdbackup.sparsestream import exceptions


class SparseStream:

    """Sparse Stream"""

    def __init__(self, types, version=2):
        """Stream version:

        1: base version
        2: stream version with compression support
        """
        self.version = version
        self.compressionMethod = "lz4"
        self.types = types.SparseStreamTypes()

    def dumpMetadata(
        self,
        virtualSize,
        dataSize,
        disk,
        checkpointName,
        parentCheckpoint,
        incremental,
        compressed,
    ):
        """First block in backup stream is Meta data information
        about virtual size of the disk being backed up

        Dumps Metadata frame to be written at start of stream in
        json format.

            Parameters:
                virtualSize:(int)       virtual size of disk
                dataSize:   (int)       used space of disk
                diskName:   (str)       name of the disk backed up
                diskFormat: (str)       disk format (raw, qcow)
                checkpointName:   (str)  checkpoint name
                compressionmethod:(str)  used compression method
                compressed:   (boolean)  flag whether if data is compressed
                parentCheckpoint: (str)  parent checkpoint
                incremental: (boolean)   whether if backup is incremental

            Returns:
                json.dumps: (str)   json encoded meta frame
        """
        meta = {
            "virtualSize": virtualSize,
            "dataSize": dataSize,
            "date": datetime.datetime.now().isoformat(),
            "diskName": disk.target,
            "diskFormat": disk.format,
            "checkpointName": checkpointName,
            "compressed": compressed,
            "compressionMethod": self.compressionMethod,
            "parentCheckpoint": parentCheckpoint,
            "incremental": incremental,
            "streamVersion": self.version,
        }
        return json.dumps(meta, indent=4).encode("utf-8")

    def writeCompressionTrailer(self, writer, trailer):
        """Dump compression trailer to end of stream"""
        size = writer.write(json.dumps(trailer).encode())
        writer.write(self.types.TERM)
        self.writeFrame(writer, self.types.COMP, 0, size)

    def _readHeader(self, reader):
        """Attempt to read header"""
        header = reader.read(self.types.FRAME_LEN)
        try:
            kind, start, length = header.split(b" ", 2)
        except ValueError as err:
            raise exceptions.BlockFormatException(
                f"Invalid block format: [{err}]"
            ) from err

        return kind, start, length

    @staticmethod
    def _parseHeader(kind, start, length):
        """Return parsed header information"""
        try:
            return kind, int(start, 16), int(length, 16)
        except ValueError as err:
            raise exceptions.FrameformatException(
                f"Invalid frame format: [{err}]"
            ) from err

    def readCompressionTrailer(self, reader):
        """If compressed stream is found, information about compressed
        block sizes is appended as last json payload.

        Function seeks to end of file and reads trailer information.
        """
        pos = reader.tell()
        reader.seek(0, os.SEEK_END)
        reader.seek(-(self.types.FRAME_LEN + len(self.types.TERM)), os.SEEK_CUR)
        _, _, length = self._readHeader(reader)
        reader.seek(-(self.types.FRAME_LEN + int(length, 16)), os.SEEK_CUR)
        trailer = self.loadMetadata(reader.read(int(length, 16)))
        reader.seek(pos)
        return trailer

    @staticmethod
    def loadMetadata(s):
        """Load and parse metadata information
        Parameters:
            s:  (str)   Json string as received during data file read
        Returns:
            json.loads: (dict)  Decoded json string as python object
        """
        try:
            meta = json.loads(s.decode("utf-8"))
        except json.decoder.JSONDecodeError as err:
            raise exceptions.MetaHeaderFormatException(
                f"Invalid meta header format: [{err}]"
            ) from err

        return meta

    def writeFrame(self, writer, kind, start, length):
        """Write backup frame
        Parameters:
            writer: (fh)    Writer object that implements .write()
        """
        writer.write(self.types.FRAME % (kind, start, length))

    def readFrame(self, reader):
        """Read backup frame
        Parameters:
            reader: (fh)    Reader object which implements .read()
        """
        kind, start, length = self._readHeader(reader)
        return self._parseHeader(kind, start, length)
