import os, re, shutil
from polyglot.builtins import iteritems

from calibre.constants import ispy3
from calibre.devices.usbms.driver import debug_print
from calibre.utils.date import now
from calibre.utils.filenames import ascii_text

#import from this plugin
from calibre_plugins.tts_to_mp3_plugin import PLUGIN_NAME    
from calibre_plugins.tts_to_mp3_plugin.common_utils import get_tag_attrib

def create_single_wav(dmp3meta, spVoice, reporter):
    ''' Create one WAV using selected Windows Sapi5 Voice at selected speech rate
        :dmp3meta:  dict of metadata related to this file
        :spVoice: calibre ISpVoice() instance. Voice to use to 'speak' the WAV
        :reporter: method to store session log 
    '''
    # extract required dmp3meta fields
    name = dmp3meta.get('name')
    safe_filename = dmp3meta.get('safe_filename')
    wav_file_name = dmp3meta.get('wav_file_name')
    booktext = dmp3meta.get('booktext')
    words = dmp3meta.get('wordcount')
    
    ts = now()
    reporter('    [%s] Processing [ispy3:%s] ... %s [%d words]' % (ts.strftime("%H:%M:%S"), ispy3, safe_filename, words))
    debug_print('{0}:do_single:Processing... {1} [{2}]'.format(
        PLUGIN_NAME, ascii_text(safe_filename), name))
    
    #create WAV file
    spVoice.create_recording_wav(wav_file_name, booktext)
    ts = now()
    reporter('    [%s] Created WAV: %s' % (ts.strftime("%H:%M:%S"), wav_file_name))

        
def create_single_mp3(dmp3meta, lame_path, reporter, parent=None):
    ''' Create one MP3 from a WAV using Windows lame.exe
        Tag MP3s using metadata from calibre library or book OPF 
        :dmp3meta:  dict of metadata related to this file
        :lame_path: path to unpacked temp copy of lame.exe 
        :reporter:  method to store session log 
    '''
    # extract required dmp3meta fields
    name = dmp3meta.get('name')
    wav_file_name = dmp3meta.get('wav_file_name')
    mp3_file_name = dmp3meta.get('mp3_file_name')
    mp3_dir = dmp3meta.get('mp3_dir')
    
    if os.path.exists(wav_file_name):
        lame_args = {k:v for (k,v) in iteritems(dmp3meta) if k.startswith('t')}
        lame_args_py3 = [lame_path]
        for tagopt, val in iteritems(lame_args):
            lame_args_py3.append('--%s' % tagopt)
            lame_args_py3.append(val)
        lame_args_py3.append(wav_file_name)
        lame_args_py3.append(mp3_file_name)
        
        # run LAME using subprocess in py3
        retcode = run_prog_py3(lame_args_py3)
        if retcode==0 and os.path.exists(mp3_file_name):
            ts = now()
            reporter('    [%s] Created MP3: %s' % (ts.strftime("%H:%M:%S"), mp3_file_name))
            
            #copy MP3 from calibre temp to user-selected dir
            shutil.copy2(mp3_file_name, mp3_dir)
            try:
                #WAVs are large, clean up calibre temp as we go
                os.remove(wav_file_name)
            except:
                pass
        else:
            reporter('*** MP3 not created: %s' % name)
    else:
        reporter('*** WAV not created: %s' % name)    
        
def run_prog_py3(list_args):
    # Run Windows executable in py3. Unicode args allowed
    import subprocess

    '''startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE'''
    cp = subprocess.run(
            list_args
            #, startupinfo=startupinfo
            , capture_output=False
            , creationflags=subprocess.CREATE_NO_WINDOW
            )
    return cp.returncode

def extract_book_meta(container, db, book_id):
    # gather all required metadata for this book
    from calibre.ebooks.oeb.polish.cover import find_cover_image
    meta = {}
    
    meta['authors'] = ['Unknown']
    meta['author_sort'] = []
    meta['title'] = 'Unknown'
    
    if book_id is not None:
        # run inside calibre library
        meta['book_id'] = book_id
        
    path_to_ebook = container.path_to_ebook
    d, fx = os.path.split(path_to_ebook)
    f, x = os.path.splitext(fx)
    meta['format'] = x[1:].upper()
    meta['path_to_ebook'] = path_to_ebook
        
    meta_fields=('authors', 'author_sort', 'title', 'title_sort', 'series', 'series_index', 'pubdate', 'tags', 'language')
    for field in meta_fields:
        val = None
        try:
            # run inside calibre library
            val = db.field_for(field, book_id)
        except:
            # run outside calibre library
            val = getattr(container.mi, field)
        if val:
            if isinstance(val, tuple):
                val = list(val)
            meta[field] = val
    
    meta['author0'] = meta['authors'][0]
    try:
        meta['author_sort'] = meta['author_sort'].split(' & ')
    except:
        pass
    
    meta['title_sort'] = meta.get('title_sort', meta.get('title'))
    meta['language'] = meta.get('language', 'en')
    
    series = meta.get('series', '')
    if series:
        series_index = meta.get('series_index', 0)
        if series_index == int(series_index):
            series_index = int(series_index)
        meta['seridx'] = series
        if series_index > 0:
            meta['seridx'] += ' %s' % series_index
        meta['series_title'] = '%s - %s' % (meta['seridx'], meta['title'])
        
    try:
        meta['pubyear'] = str(meta.get('pubdate').year).zfill(4)
    except:
        pass
    
    cover_data = None
    try:
        cover_data = db.cover(book_id)
    except:
        pass
    
    if cover_data is None:
        cover_img_name = find_cover_image(container)
        if cover_img_name:
            cover_data = container.raw_data(cover_img_name)
            
    meta['cover_data'] = cover_data
        
    return meta

def get_page_text(container, name, img_alt=False, alt_prefix=''):
    ''' return text-only unicode string for selected page 
        :img_alt: bool, force-add <img alt="xyz" .../> text to extracted text
        :alt_prefix: text to be used to announce that img alt text follows
    '''
    from calibre.ebooks.oeb.base import xml2text, XHTML
    text = ''
    root = container.parsed(name)
    if not hasattr(root, 'xpath'):
        return ''
    
    body = get_tag_attrib(root, tag='body', first_only=True)
    if body is not None:
        brs = get_tag_attrib(root, tag='br')
        for br in brs:
            tail = br.tail if br.tail else ''
            br.tail = '\n' + tail
        
        if img_alt:
            imgs = get_tag_attrib(root, tag='img')
            for img in imgs:
                alt = img.attrib.get('alt', '').strip()
                if alt:
                    img.attrib.clear()
                    img.tag = XHTML('span')
                    img.text = ' [%s] ' % alt
                    # only add prefix if alt text doesn't start with same text
                    if alt_prefix and not alt.lower().startswith(alt_prefix.lower()):
                        img.text = ' [%s: %s] ' % (alt_prefix, alt)                        
        text = xml2text(body)
        # remove excess empty lines
        text = re.sub(r'[\s\xa0]+\n', '\n\n', text)
    return text.strip() if text else ''

def get_voiceid_from_desc(sapi, desc=None):
    # get the Voice id from Voice description
    ids = []
    all_voices = sapi.get_all_voices()
    if desc is not None:
        ids = [dv['id'] for dv in all_voices if desc in dv['description']]
    return ids[0] if ids else sapi.get_current_voice()

'''
def get_voicedesc_from_id(sapi, id=None):
    # get the Voice description from the Voice id (Win registry key)
    all_voices = sapi.get_all_voices()
    default_voice_id = sapi.get_current_voice()
    id = id if id is not None else default_voice_id
    descs = [dv['description'] for dv in all_voices if id==dv['id']]
    return descs[0] if descs else default_voice_id.split(os.sep)[-1]
'''

def get_sorted_voicedescs(sapi):
    # get list of installed Voice descriptions sorted by Language/Gender
    all_voices = sapi.get_all_voices()
    vlist = [(dv['language'], dv['gender'], dv['description']) for dv in all_voices]
    return [desc for (lang, gen, desc) in sorted(vlist)]
