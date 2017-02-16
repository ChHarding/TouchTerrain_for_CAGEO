"""
InMemoryZip class

Thanks to Anthon
http://stackoverflow.com/questions/2463770/python-in-memory-zip-library
""" 

import zipfile
try:
    from cStringIO import StringIO
except ImportError:
    from io import BytesIO as StringIO

class InMemoryZip(object):
    def __init__(self):
        # Create the in-memory file-like object
        self.in_memory_data = StringIO()
        
        # Create the in-memory zipfile
        self.in_memory_zip = zipfile.ZipFile(self.in_memory_data, "w", zipfile.ZIP_DEFLATED, False)
        self.in_memory_zip.debug = 3

    def append(self, filename_in_zip, file_contents):
        '''Appends a file with name filename_in_zip and contents of
        file_contents to the in-memory zip.'''
        self.in_memory_zip.writestr(filename_in_zip, file_contents)
        return self   # so you can daisy-chain

    def writetofile(self, filename):
        '''Writes the in-memory zip to a file'''
        # Mark the files as having been created on Windows so that Unix permissions are not inferred as 0000
        for zfile in self.in_memory_zip.filelist:zfile.create_system = 0
        self.in_memory_zip.close()
        with open(filename, 'wb') as f:
            f.write(self.in_memory_data.getvalue())

            
    def get_string_buffer(self):
        '''closes the in-memory zip and returns as a string buffer'''
        # Mark the files as having been created on Windows so that Unix permissions are not inferred as 0000
        for zfile in self.in_memory_zip.filelist:zfile.create_system = 0
        self.in_memory_zip.close()
        return self.in_memory_data.getvalue() # close() to free memory ?

        

if __name__ == "__main__":

    data =  "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" * 1024
    imz = InMemoryZip()
    imz.append("file1.obj", "# objfile 1\n" + data)
    imz.append("file2.obj", "# objfile 1\n" + data)
    mbuf = imz.get_zip_as_StringIO()
    print type(mbuf)
    imz.close()