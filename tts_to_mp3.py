import os, shutil, re
import traceback

from polyglot.builtins import as_unicode

try:
    from qt.core import (
        Qt, QDialog, QProgressDialog, QTimer, QIcon,
        QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QDialogButtonBox, 
        QLabel, QPushButton, QComboBox, QSpinBox, QPixmap, QMessageBox)
except ImportError:
    from PyQt5.Qt import (
        Qt, QDialog, QProgressDialog, QTimer, QIcon,
        QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QDialogButtonBox, 
        QLabel, QPushButton, QComboBox, QSpinBox, QPixmap, QMessageBox)

from calibre import sanitize_file_name_unicode
from calibre.devices.usbms.driver import debug_print
from calibre.ebooks.oeb.polish.check.parsing import make_filename_safe
from calibre.ebooks.oeb.polish.container import get_container
from calibre.ebooks.oeb.polish.pretty import pretty_all
from calibre.gui2 import choose_dir
from calibre.gui2 import error_dialog, info_dialog, warning_dialog
from calibre.ptempfile import PersistentTemporaryDirectory
from calibre.spell.break_iterator import count_words
from calibre.utils.date import now
from calibre.utils.img import save_cover_data_to
from calibre_extensions.winsapi import ISpVoice


#import from this plugin
from calibre_plugins.tts_to_mp3_plugin import PLUGIN_NAME, PLUGIN_CAPTION
from calibre_plugins.tts_to_mp3_plugin.config import prefs
from calibre_plugins.tts_to_mp3_plugin.other_dlgs import SelNamesDlg
from calibre_plugins.tts_to_mp3_plugin.utils import (
    extract_book_meta, get_page_text, 
    get_sorted_voicedescs, get_voiceid_from_desc)
from calibre_plugins.tts_to_mp3_plugin.common_utils import (
    find_icon, extract_executable, get_toc_dict_list)
 
PROG_FILENAME = 'lame.exe'


class EbookTTStoMP3(QDialog):
    ''' Create set of TTS audiobook MP3s using LAME utility, 1 per selected text file
        Use selected Windows-installed Sapi Voice at selected speech rate
        Tag MP3s using metadata from calibre library (if available)
        or from book's OPF file otherwise
    '''

    def __init__(self, gui, pathtoebook, book_id=None):
        QDialog.__init__(self, parent=gui)

        self.gui = gui
        self.pathtoebook = pathtoebook
        self.book_id = book_id
        self.db = None
        if self.book_id:
            self.db = self.gui.current_db.new_api
        
        self.container = None
        self.dest_dir = PersistentTemporaryDirectory('_ttsmp3')
        self.mp3_dir = None
        self.selected_names = []
        self.tempdir = None
        self.lame_path = None
        self.book_meta = {}
        self.spVoice = ISpVoice()
        self.all_voices = self.spVoice.get_all_voices()
        self.vid = None
        self.voice_name = None
        self.voice_rate = 0
        self.spinelistdict = []
        self.spine_list = []
        self.toc_name_title_map = {}
        self.book_data_map = {}
        self.name_data_map = {}
        self.payload = []
        self.book_label = ''

        self.setWindowTitle(PLUGIN_CAPTION)
        icon = find_icon('images/plugin_icon.png')
        self.setWindowIcon(icon)
        
        # create widgets
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Save).setText('Create MP&3s')

        self.buttonBox.button(QDialogButtonBox.StandardButton.Save).setIcon(icon)
        
        aboutButton = QPushButton('About', self)
        self.bookLabel = QLabel()
        
        metasrc = '(from ebook internal OPF)' if not self.book_id else ''
        gpmeta = QGroupBox('Book metadata: %s' % metasrc)
        laymeta = QGridLayout()
        gpmeta.setLayout(laymeta)
        
        self.metas = {}
        i = 0
        for m in ('authors', 'title', 'series','pubdate', 'tags', 'format'):
            label = QLabel('<b>%s:</b>' % m.title())
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setMaximumWidth(60)
            laymeta.addWidget(label, i, 0)
            widget = QLabel('')
            widget.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            widget.setWordWrap(True)
            laymeta.addWidget(widget, i, 1)
            self.metas[m] = widget
            i += 1
        
        gpmp3tag = QGroupBox('MP3 tags:')
        laymp3tag = QGridLayout()
        gpmp3tag.setLayout(laymp3tag)
        
        self.mp3tags = {}
        i = 0
        for lameopt, tag in [('ta', 'Artist'),
                            ('tl', 'Album'), 
                            ('ty', 'Year'), 
                            ('tg', 'Genre'), 
                            ('tc', 'Comment')]:
            label = QLabel('<b>%s:</b>' % tag)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setMaximumWidth(60)
            laymp3tag.addWidget(label, i, 0)
            
            if lameopt == 'tc':
                widget = QLabel(tag)
                widget.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            else:
                widget = QComboBox()
                widget.setEditable(True)
                widget.currentTextChanged.connect(self.refresh_mp3tags)

            laymp3tag.addWidget(widget, i, 1)
            self.mp3tags[lameopt] = widget
            i += 1
        
        self.coverLabel = QLabel('')
        
        gpvoice = QGroupBox('Select Voice and Speech Rate:')
        layvoice = QGridLayout()
        gpvoice.setLayout(layvoice)
        
        self.voiceCombo = QComboBox()
        
        self.rateSpin = QSpinBox()
        self.rateSpin.setRange(-10, 10)
        self.rateSpin.setToolTip('Range (-10, 10)')
        self.rateSpin.setSingleStep(1)
        
        rateLabel = QLabel('Speech &Rate:')
        rateLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rateLabel.setBuddy(self.rateSpin)
        
        voiceLabel = QLabel('&Voice:')
        voiceLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        voiceLabel.setBuddy(self.voiceCombo)
        
        layvoice.addWidget(voiceLabel, 0, 0)
        layvoice.addWidget(self.voiceCombo, 0, 1, 1, 3)
        layvoice.addWidget(rateLabel, 1, 0)
        layvoice.addWidget(self.rateSpin, 1, 1)
        
        gpfiles = QGroupBox('Select files to record to MP3:')
        layfiles = QGridLayout()
        gpfiles.setLayout(layfiles)
        
        selspineButton = QPushButton("&Manual select")
        selspineButton.setToolTip("Useful for excluding front/backmatter")
        allfilesButton = QPushButton("&All")
        allfilesButton.setToolTip("All files which actually contain text")
        self.totfilesLabel = QLabel('')
        self.avgwordsLabel = QLabel('')
        
        layfiles.addWidget(selspineButton, 0, 0)
        layfiles.addWidget(allfilesButton, 1, 0)
        layfiles.addWidget(self.totfilesLabel, 0, 1)
        layfiles.addWidget(self.avgwordsLabel, 1, 1)
        
        grid = QGridLayout()
        grid.addWidget(self.bookLabel, 0, 0, 1, 2)
        grid.addWidget(aboutButton, 0, 2)
        
        grid.addWidget(gpmeta, 1, 0)
        grid.addWidget(gpmp3tag, 1, 1)
        grid.addWidget(self.coverLabel, 1, 2, 2, 1)
                
        grid.addWidget(gpvoice, 3, 1)
        grid.addWidget(gpfiles, 3, 0)
        
        grid.addWidget(self.buttonBox, 9, 0, 1, 3)
        self.setLayout(grid)
        
        # create connect signals/slots
        aboutButton.clicked.connect(self.aboutButton_clicked)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.voiceCombo.currentTextChanged.connect(self.voiceCombo_textChanged)
        self.rateSpin.valueChanged.connect(self.rateSpin_valueChanged)
        selspineButton.clicked.connect(self.selspineButton_clicked)
        allfilesButton.clicked.connect(self.allfilesButton_clicked)

        try:
            self.container = get_container(self.pathtoebook)
            book_type = self.container.book_type
        except:
            book_type = None
            
        errmsg = ''
        if book_type not in ('epub', 'azw3', 'kepub'):
            errmsg = '%s\n\n*** Unsupported book format. Must be EPUB, AZW3, KEPUB.' % self.pathtoebook
            error_dialog(self.gui, PLUGIN_NAME,
                errmsg, show=True, show_copy_button=True)
        else:    
            self.initialise_data()
            if not self.all_voices:
                errmsg = '\n*** The plugin cannot detect any voices to use for TTS on this PC'
                warning_dialog(self.gui, PLUGIN_NAME,
                    errmsg, show=True, show_copy_button=True)
            elif not self.lame_path:
                errmsg = '\n*** Could not find %s' % PROG_FILENAME
                error_dialog(self.gui, PLUGIN_NAME,
                    errmsg, show=True, show_copy_button=True)
        
    def initialise_data(self):
        # Tidy up the HTML code to avoid problems with too few line breaks
        # and convert any HTML entities to unicode
        
        pretty_all(self.container)
        
        # need a temp dir to store lame.exe
        self.tempdir = os.path.dirname(self.container.root)
        
        # extract lame.exe from plugin.zip and save in temp dir
        self.lame_path = extract_executable(self.tempdir, PROG_FILENAME, plugin=PLUGIN_NAME)
        
        # search Windows for descriptions of all available Voices
        all_descs = get_sorted_voicedescs(self.spVoice)
        self.voiceCombo.addItems(all_descs)
        
        vname = prefs['voice_name']
        if vname not in all_descs:
            # set to first voice name in combo
            vname = all_descs[0]
            prefs['voice_name'] = vname
        self.voice_name = vname
        self.vid = get_voiceid_from_desc(self.spVoice, vname)
        self.spVoice.set_current_voice(self.vid)
        
        self.voice_rate = prefs['voice_rate']
        self.spVoice.set_current_rate(self.voice_rate)
        
        self.voiceCombo.setCurrentText(self.voice_name)
        self.rateSpin.setValue(self.voice_rate)
        
        # build book metadata dict from calibre library (if avail) or from book OPF
        self.book_meta = extract_book_meta(self.container, self.db, self.book_id)
        
        # build MP3 tag options from book meta
        artist_opts = set()
        for meta in ('authors', 'author_sort'):
            listmeta = [x for x in self.book_meta.get(meta)]
            [artist_opts.add(a) for a in self.book_meta.get(meta, [])]
            artist_opts.add(' & '.join(self.book_meta.get(meta, [])[:3]))
            
        self.mp3tags['ta'].addItems(sorted(artist_opts))
        self.mp3tags['ta'].setCurrentText(self.book_meta.get('author0'))
        
        album_opts = set([self.book_meta.get(meta) for meta in ('title', 'title_sort', 'series_title') if self.book_meta.get(meta, None)])
        self.mp3tags['tl'].addItems(sorted(album_opts))
        self.mp3tags['tl'].setCurrentText(self.book_meta.get('series_title', self.book_meta.get('title')))
        
        thisyr = now().strftime("%Y")
        year = self.book_meta.get('pubyear', thisyr)
        year_opts = set([year, thisyr])
        self.mp3tags['ty'].addItems(sorted(year_opts))
        self.mp3tags['ty'].setCurrentText(year)
        
        genre_opts = set(['Speech'] + self.book_meta.get('tags', []))
        self.mp3tags['tg'].addItems(sorted(genre_opts))
        self.mp3tags['tg'].setCurrentText('Speech')
            
        self.display_book_meta()
        
        # create thumbnail of cover image
        cover_data = self.book_meta.get('cover_data', None)
        self.book_data_map['ti'] = None
        if cover_data is not None:
            pixmap = QPixmap()
            pixmap.loadFromData(cover_data)
            self.coverLabel.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio))
            
            thumbnail = 'embed.jpg' if prefs['embed_cover_thumbnail'] else 'cover.jpg'
            
            thumb_path = os.path.join(self.dest_dir, thumbnail)
            self.book_data_map['ti'] = thumb_path
            save_cover_data_to(cover_data, path=thumb_path, minify_to=(300, 300))

        # create a map of name:toctitle for each container name
        #   if file has multiple TOC entries, use 1st one
        #   if file is not in TOC use name (excl. dir and ext)
        toc_dl = get_toc_dict_list(self.container)
        self.toc_name_title_map = {d['name']: '{0}{1}'.format(3*'\xa0'*(d['level']-1), d['title']) for d in reversed(toc_dl)}
        
        self.spine_list = [name for name, x in self.container.spine_names]
        
        max_files = len(self.spine_list)
        padding = len(str(max_files))

        language = self.book_meta.get('language')

        # build metadata dict per spine text file
        track = 1
        for name in self.spine_list:
            self.name_data_map[name] = self.populate_name_data_map(name, track, padding, language, prefs['img_alt_show'], prefs['img_alt_prefix'])
            if self.name_data_map[name].get('booktext'):
                track += 1
            
        self.refresh_filecount()
        
        # build the row table to be used with the QDialog for selecting which files to convert to MP3
        self.spinelistdict = [
            {'name': name, 
            'toc': self.name_data_map[name]['short_toctitle'], 
            'sample': self.name_data_map[name]['sample'],
            'wordcount': self.name_data_map[name]['wordcount']
            } for name in self.spine_list]
        
        self.book_label = self.book_meta.get('path_to_ebook')
        if self.book_id:
            self.book_label = '%s - %s (%s)' % (self.book_meta.get('author0'), self.book_meta.get('title'), self.book_id)
        self.bookLabel.setText(self.book_label)
            
    def voiceCombo_textChanged(self, text):
        self.voice_name = text
        self.vid = get_voiceid_from_desc(self.spVoice, text)
        self.spVoice.set_current_voice(self.vid)
        self.refresh_mp3_comment()
            
    def rateSpin_valueChanged(self, int):
        self.spVoice.set_current_rate(int)
        self.voice_rate = int
        self.refresh_mp3_comment()
                
    def allfilesButton_clicked(self):
        self.selected_names = [name for name in self.spine_list if self.name_data_map[name].get('booktext', '')]
        self.refresh_filecount()
        
    def selspineButton_clicked(self):
        dialog = SelNamesDlg(self.selected_names, self.spinelistdict, self.name_data_map, self.voice_name, self.voice_rate, self)
        if dialog.exec_():
            # force selected names into spine sequence
            self.selected_names = [name for name in self.spine_list if name in dialog.select_spines]
            self.refresh_filecount()

            #set main dialog voice values to same as Select/TestVoice dialog values
            self.voiceCombo.setCurrentText(dialog.vname)
            self.rateSpin.setValue(dialog.vrate)

    def prep_to_create_mp3s(self):
        # save voice settings to config file
        prefs['voice_name'] = self.voice_name
        prefs['voice_rate'] = self.voice_rate
            
        mp3_dir = choose_dir(self.gui, name='tts_to_mp3_plugin', title='Destination directory for MP3s')
        if not mp3_dir:
            return False
            
        # create a sanitised subdir for MP3s based on book title
        self.mp3_dir = mp3_dir
        #self.dest_dir = PersistentTemporaryDirectory('_ttsmp3')
        album = self.book_data_map.get('tl', '').strip()
        if album:
            clean_album = sanitize_file_name_unicode(album).strip('_')
            clean_album = make_filename_safe(clean_album)
            clean_album = re.sub(r'[_]{2,}', '_', clean_album)
            clean_album = clean_album.replace('_', ' ').strip()
            self.mp3_dir = os.path.join(self.mp3_dir, clean_album)
            if not os.path.exists(self.mp3_dir):
                os.mkdir(self.mp3_dir)
        
        # process cover thumbnail
        thumb_path = os.path.join(self.dest_dir, 'cover.jpg')
        if os.path.exists(thumb_path):
            shutil.copy2(thumb_path, self.mp3_dir)
            
        #build the 'to-do' list of names/metadata in prep for using a QProgressDialog
        self.create_payload()
        if not self.payload:
            errmsg = '\n*** Nothing to record to MP3. None of the selected files contain text.'
            info_dialog(self.gui, PLUGIN_NAME,
                errmsg, show=True, show_copy_button=True)
            return False
        return True
        
    def create_payload(self):
        #build the 'to-do' list of names/metadata in prep for using a QProgressDialog
        self.payload = []
        for name in self.selected_names:
            booktext = self.name_data_map[name].get('booktext', '')
            if booktext:
                safe_filename = self.name_data_map[name].get('safe_filename')
                wav_file_name = os.path.join(self.dest_dir, safe_filename + '.wav')
                mp3_file_name = os.path.join(self.dest_dir, safe_filename + '.mp3')
                
                dmp3meta = {
                        'name':name
                        , 'book_id':self.book_id
                        , 'booktext': booktext
                        , 'safe_filename': safe_filename
                        , 'wav_file_name': wav_file_name
                        , 'mp3_file_name': mp3_file_name
                        , 'pad_track': self.name_data_map[name].get('pad_track')
                        , 'wordcount': self.name_data_map[name].get('wordcount')
                        , 'mp3_dir': self.mp3_dir
                        }
                
                for lameopt in ('ta', 'tl', 'ty', 'tg', 'tc'):
                    dmp3meta[lameopt] = self.book_data_map.get(lameopt)
                    
                if prefs['embed_cover_thumbnail']:
                    thumb_path = self.book_data_map.get('ti')
                    if thumb_path is not None:
                        dmp3meta['ti'] = thumb_path
                    
                for lameopt in ('tt', 'tn'):
                    dmp3meta[lameopt] = self.name_data_map[name].get(lameopt)
            
                for k,v in sorted(dmp3meta.items()):
                    if k != 'booktext':
                        debug_print('{0}: {1}'.format(k, v))
                    
                self.payload.append(dmp3meta)
        
    def refresh_mp3_comment(self):
        shortnames = [dv['name'] for dv in self.all_voices if dv['id'] == self.vid]
        shortname = shortnames[0] if shortnames else 'Unknown'
        comment = 'calibre: %s (%d)' % (shortname, self.voice_rate)
        self.mp3tags['tc'].setText(comment.strip())
        self.refresh_mp3tags()
        
    def refresh_filecount(self):
        self.buttonBox.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        if self.selected_names:
            self.buttonBox.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)
            
        words = [self.name_data_map[name].get('wordcount', 0) for name in self.selected_names]
        files_with_words = len(words) - words.count(0)
        total_words = sum(words)
        avg_words = float(total_words) / files_with_words if files_with_words else 0
        
        self.totfilesLabel.setText('Selected: {0} / {1}'.format(len(self.selected_names), len(self.spine_list)))
        self.avgwordsLabel.setText('Avg. words/file: {0:.0f}'.format(avg_words))
        
    def refresh_mp3tags(self):
        # extract book data for mp3 tags
        for lameopt in ('ta', 'tl', 'ty', 'tg', 'tc'):
            if hasattr(self.mp3tags[lameopt], 'currentText'):
                self.book_data_map[lameopt] = self.mp3tags[lameopt].currentText()
            elif hasattr(self.mp3tags[lameopt], 'text'):
                self.book_data_map[lameopt] = self.mp3tags[lameopt].text()
        
    def display_book_meta(self):
        self.metas['authors'].setText(' & '.join(self.book_meta.get('authors', [])))
        self.metas['title'].setText(self.book_meta.get('title', ''))
        self.metas['format'].setText(self.book_meta.get('format', ''))
        self.metas['series'].setText(self.book_meta.get('seridx', ''))
        self.metas['pubdate'].setText(self.book_meta.get('pubyear', ''))
        self.metas['tags'].setText(', '.join(self.book_meta.get('tags', [])))
            
    def populate_name_data_map(self, name, track, padding, language, img_alt_show, img_alt_prefix):
        dict = {}
        d, fx = os.path.split(name)
        f, x = os.path.splitext(fx)
        sanfname = sanitize_file_name_unicode(f)

        toctitle = self.toc_name_title_map.get(name, '')
        if not toctitle:
            # this text file is missing from the TOC
            toctitle = sanfname
            dict['tt'] = sanfname
        else:
            dict['tt'] = toctitle.strip()
            sanfname = sanitize_file_name_unicode(toctitle.strip())
            if len(toctitle) > 50:
                toctitle = toctitle[:50] + '...'
            
        dict['short_toctitle'] = toctitle
        
        safe_fname = make_filename_safe(sanfname)
        safe_fname1 = re.sub(r'[_]{2,}', '_', safe_fname)[:50]
        safe_fname2 = safe_fname1.replace('_', ' ').strip()
        
        raw_data = self.container.raw_data(name)
        dict['sample'] = raw_data[:1000] + '...'
            
        booktext = get_page_text(self.container, name, img_alt=img_alt_show, alt_prefix=img_alt_prefix)
        
        dict['booktext'] = booktext
        
        wordcount = count_words(booktext.replace('.', '. '), language)
        dict['wordcount'] = wordcount
        
        dict['tn'] = '0'
        dict['pad_track'] = '0'.zfill(padding)
        dict['safe_filename'] = ''
        if booktext:
            dict['tn'] = str(track)
            dict['pad_track'] = str(track).zfill(padding)
            dict['safe_filename'] = '%s_%s' % (dict['pad_track'], safe_fname2)

        return dict
    
    def aboutButton_clicked(self):
        # Get the about text from a file inside the plugin zip file
        # The get_resources function is a builtin function defined for all your
        # plugin code. It loads files from the plugin zip file. It returns
        # the bytes from the specified file.
        #
        # Note that if you are loading more than one file, for performance, you
        # should pass a list of names to get_resources. In this case,
        # get_resources will return a dictionary mapping names to bytes. Names that
        # are not found in the zip file will not be in the returned dictionary.
        
        ver = PLUGIN_CAPTION
        try:
            text = as_unicode(get_resources('about.txt'))
        except:
            text = 'Utility to record audiobook MP3 files from selected text files in an ebook.'
            text += '\nUses Microsoft SAPI5 Voices and Text-to-Speech.'
            text += '\n\n[EPUB, AZW3 or KEPUB formats only]'
            ver += ' standalone'
        QMessageBox.about(self, 'About %s' % ver, text)

    def accept(self):
        ok_to_proceed = self.prep_to_create_mp3s()
        if ok_to_proceed:
            QDialog.accept(self)
        
class QueueProgressDialog(QProgressDialog):
    # MP3 creation run in background via calibre jobs system        
    def __init__(self, gui, payload, queue, djobmeta):
        self.total_files = len(payload)
        QProgressDialog.__init__(self, '', '', 0, self.total_files, gui)
        
        self.gui = gui
        self.payload = payload
        self.djobmeta = djobmeta
        self.queue = queue
        
        self.files_to_proc, self.bad_files = [], []
        
        self.setWindowTitle('Queueing files for {0}'.format(PLUGIN_NAME))
        self.setMinimumWidth(500)
        
        self.i = 0
        QTimer.singleShot(0, self.do_file_action)
        self.exec_()

    def do_file_action(self):
        if self.i >= self.total_files:
            return self.do_queue()
            
        # get data for current file
        dmp3meta = self.payload[self.i]
        pad_track = dmp3meta.get('pad_track')
        name = dmp3meta.get('name')
        book_label = self.djobmeta.get('book_label')
        try:
            self.setLabelText(_('Queueing ') + pad_track + name)
            self.files_to_proc.append((dmp3meta, self.djobmeta))
            self.setValue(self.i)
        except:
            traceback.print_exc()
            self.bad_files.append((pad_track, name, 'tts_to_mp3:Unknown error', book_label))

        self.i += 1
        QTimer.singleShot(0, self.do_file_action)

    def do_queue(self):
        if self.gui is None:
            # There is a nasty QT bug with the timers/logic above which can
            # result in the do_queue method being called twice
            return
        self.hide()
        if not self.files_to_proc:
            warning_dialog(self.gui, 'Scan failed',
                'No files found which match chosen criteria.',
                show_copy_button=False, show=True)
        self.gui = None
        if self.files_to_proc:
            # Queue a job to process these books
            self.queue(self.files_to_proc, self.bad_files)

if __name__ == "__main__":
    import sys, re
    from qt.core import QApplication
    
    pathtoebook = sys.argv[1]

    app = QApplication(sys.argv)
    w = EbookTTStoMP3(None, pathtoebook)
    w.show()
    app.exec()