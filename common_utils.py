# Get required support modules for all plugin actions
import os
import re
import shutil

from polyglot.builtins import (iterkeys, itervalues, iteritems,
    as_bytes, as_unicode, unicode_type)

from calibre.devices.usbms.driver import debug_print
#from calibre.utils.date import now

# Global definition of our plugin name. 
# Used for common functions that require this.
plugin_name = None
plugin_caption = None

def set_plugin_globals(name, caption):
    '''
    Set our global store of plugin name and icon resources for sharing between
    the InterfaceAction class which reads them and the ConfigWidget
    if needed for use on the customization dialog for this plugin.
    '''
    global plugin_name, plugin_caption
    plugin_name = name
    plugin_caption = caption


def find_icon(ipath):
    import os
    
    try:
        from qt.core import QIcon
    except ImportError:
        from PyQt5.Qt import QIcon
    
    # Find the best icon available for the plugin PNGname supplied
    #   by looking first in config/resources/images 
    #   for custom images for this plugin
    # If no custom image found, use the one in the plugin
    
    global plugin_name
    
    # handle nested dirs of plugin images
    pngname = '/'.join(ipath.split('/')[1:])
    pngname = pngname if pngname else ipath
    
    # use calibre standard I function to look for user custom images
    custname = '{0}/{1}'.format(plugin_name, pngname)
    cname = I(custname)
    if os.path.exists(cname):
        # use custom image
        icon = QIcon(cname)
    else:
        # use plugin image
        icon = get_icons(ipath)
    return icon


def get_tag_attrib(root, tag=None, attrib=None, value=None, first_only=False):
    ''' utility to select elements from a parsed HTML file '''
    if tag is not None:
        if attrib is not None:
            if value is not None:
                items = root.xpath('//*[local-name()="%s" and @%s="%s"]' % (tag, attrib, value))
            else:
                items = root.xpath('//*[local-name()="%s" and @%s]' % (tag, attrib))
        else:
            items = root.xpath('//*[local-name()="%s"]' % tag)
    else:
        if attrib is not None:
            if value is not None:
                items = root.xpath('//*[@%s="%s"]' % (attrib, value))
            else:
                items = root.xpath('//*[@%s]' % attrib)
        else:
            return None
        
    if first_only:
        return items[0] if items else None
    return items

def extract_executable(prog_tempdir, prog_filename, plugin=None, extractall=False):
    from calibre.utils.config import config_dir
    from calibre.utils.zipfile import ZipFile
        
    if not plugin:
        return None
        
    plugin_zip = '{0}.zip'.format(plugin)
    prog_path = os.path.join(prog_tempdir, prog_filename)

    # unzip executable from plugin zip to tempdir
    if not os.path.exists(prog_path):
        try:
            plugin_zip_path = os.path.join(config_dir, 'plugins', plugin_zip)
            with ZipFile(plugin_zip_path, 'r') as zf:
                if extractall:
                    zf.extractall(prog_tempdir)
                else:
                    #extract only the named executable filename
                    zf.extract(prog_filename, prog_tempdir)
                    
            debug_print('{0}:extract_executable: {1} from {2} to {3}'.format(
                plugin, prog_filename, plugin_zip_path, prog_tempdir))
            debug_print('{0}:extract_executable: {1}'.format(plugin, prog_path))
        except:
            pass
    return prog_path if os.path.exists(prog_path) else None

def get_toc_dict_list(container):
    from calibre.ebooks.oeb.polish.toc import get_toc
    
    def toc_details_recursive(ctoc, level=0):    
        if ctoc.dest:
            name = container.href_to_name(ctoc.dest)
            tocd = {'name': name,
                    'level': level,
                    'title': ctoc.title,
                    'dest': ctoc.dest,
                    'dest_exists': ctoc.dest_exists,
                    'frag': ctoc.frag}
            ans = [tocd]
        else:
            ans = []
            
        for child in ctoc:
            ans.extend(toc_details_recursive(child, level+1))
        return ans
    
    toc = get_toc(container)
    toc_dict_list = toc_details_recursive(toc)
    return toc_dict_list
