__license__   = 'GPL v3'
__copyright__ = '2011, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

'''if False:
    # This is here to keep my python error checker from complaining about
    # the builtin functions that will be defined by the plugin loading system
    # You do not need this code in your plugins
    get_icons = get_resources = None'''

import os
import shutil
from glob import glob

from polyglot.builtins import unicode_type, iteritems

try:
    from qt.core import (
        QMenu, QToolButton, QIcon,
        QDialog, QLabel, QDialogButtonBox,
        QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton)
except ImportError:
    from PyQt5.Qt import (
        QMenu, QToolButton, QIcon,
        QDialog, QLabel, QDialogButtonBox,
        QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton)
    
# The class that all interface action plugins must inherit from
from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog, open_local_file
from calibre.gui2.proceed import Icon
from calibre.gui2.dialogs.message_box import ErrorNotification
#from calibre.utils.date import now

from calibre_plugins.tts_to_mp3_plugin import PLUGIN_NAME, PLUGIN_CAPTION, PLUGIN_DESCRIPTION
#from calibre_plugins.tts_to_mp3_plugin.config import prefs
from calibre_plugins.tts_to_mp3_plugin.tts_to_mp3 import EbookTTStoMP3, QueueProgressDialog
from calibre_plugins.tts_to_mp3_plugin.jobs import get_job_details
from calibre_plugins.tts_to_mp3_plugin.other_dlgs import EbookSelectFormat
from calibre_plugins.tts_to_mp3_plugin.common_utils import set_plugin_globals, find_icon

OK_FORMATS = ('EPUB', 'AZW3', 'KEPUB')

class TTSMP3UiAction(InterfaceAction):
    name = PLUGIN_NAME

    # Declare the main action associated with this plugin
    # The keyboard shortcut can be None if you dont want to use a keyboard
    # shortcut. Remember that currently calibre has no central management for
    # keyboard shortcuts, so try to use an unusual/unused shortcut.
    
    # Create our top-level menu/toolbar action (text, icon_path, tooltip, keyboard shortcut)
    action_spec = (PLUGIN_NAME, None, PLUGIN_DESCRIPTION, ())
    
    dont_add_to = frozenset(['context-menu-device', 'toolbar-device', 'menubar-device'])
    dont_remove_from = frozenset([])
    popup_type = QToolButton.MenuButtonPopup
    action_type = 'current'
    
    book_label = 'Unknown'

    def genesis(self):
        # This method is called once per plugin, do initial setup here
        set_plugin_globals(self.name, PLUGIN_CAPTION)
        
        self.is_library_selected = True
        self.menu = QMenu(self.gui)
        
        # Set the icon for this interface action
        # The get_icons function is a builtin function defined for all your
        # plugin code. It loads icons from the plugin zip file. It returns
        # QIcon objects, if you want the actual data, use the analogous
        # get_resources builtin function.
        #
        # Note that if you are loading more than one icon, for performance, you
        # should pass a list of names to get_icons. In this case, get_icons
        # will return a dictionary mapping names to QIcons. Names that
        # are not found in the zip file will result in null QIcons.
        
        self.icons = get_icons(['images/plugin_icon.png',
                                'images/play.png',
                                'images/stop.png'
                                ])
            
        # The qaction is automatically created from the action_spec defined above
        self.rebuild_menu()
        self.qaction.setMenu(self.menu)
        
        icon = find_icon('images/plugin_icon.png')
        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.show_dialog)
        
    def location_selected(self, loc):
        self.is_library_selected = loc == 'library'

    def apply_settings(self):
        # In an actual non trivial plugin, you would probably need to
        # do something based on the settings in prefs, e.g. rebuild menus
        # prefs
        pass
        
    def library_changed(self, db):
        self.rebuild_menu()
            
    def rebuild_menu(self):
        m = self.menu
        m.clear()
        
        ac1 = self.create_action(
                spec=(PLUGIN_NAME, None, None, None),
                attr=PLUGIN_NAME)
        icon = find_icon('images/plugin_icon.png')
        ac1.setIcon(icon)
        ac1.triggered.connect(self.show_dialog)
        m.addAction(ac1)
        
        m.addSeparator()
        ac2 = self.create_action(
                spec=('Customize plugin...', 'config.png', None, None),
                attr='Customize plugin...')
        ac2.triggered.connect(self.show_configuration)
        m.addAction(ac2)
        
    def show_configuration(self):
        self.interface_action_base_plugin.do_user_config(self.gui)
                                
    def show_dialog(self):
        
        class SelectedBookError(Exception): pass
        
        # Selected book checks. If error raise SelectedBookError
        # Get book from currently selected row. Only single row is valid
        try:
            #rows = self.gui.current_view().selectionModel().selectedRows()
            book_ids = self.gui.library_view.get_selected_ids()
            
            if not book_ids or len(book_ids) == 0:
                errmsg = 'No book selected'
                raise SelectedBookError(errmsg)
                
            if len(book_ids) > 1:
                errmsg = 'More than one book selected'
                raise SelectedBookError(errmsg)
                
            #if self.is_library_selected:
            book_id = book_ids[0]
                
            # check which formats exist and select only one
            db = self.gui.current_db.new_api
            avail_fmts = db.formats(book_id, verify_formats=True)
            valid_fmts = [f for f in OK_FORMATS if f in avail_fmts]
            
            if len(valid_fmts) > 1:
                msg = '\nThis book has multiple suitable formats.\n' \
                        'Please select one of the following:\n'
                seldlg = EbookSelectFormat(self.gui, valid_fmts, msg, self.gui)
                if seldlg.exec_():
                    valid_fmts = seldlg.result
                
            try:
                fmt = valid_fmts[0]
                path_to_ebook = db.format(book_id, fmt, as_path=True, preserve_filename=True)
            except:
                path_to_ebook = None

            if not path_to_ebook:
                errmsg = 'No %s available for this book' % ', '.join(OK_FORMATS)
                raise SelectedBookError(errmsg)
        
        except SelectedBookError as err:
            return error_dialog(self.gui,
                        '%s: Book selection error' % PLUGIN_CAPTION,
                        str(err), show=True)

        # all OK, proceed with action
        
        # get all user GUI input
        dlg = EbookTTStoMP3(self.gui, path_to_ebook, book_id=book_id)
        
        if dlg.exec_():
            self.book_label = dlg.book_label
            
            djobmeta = {'lame_path': dlg.lame_path
                        , 'voice_name': dlg.voice_name
                        , 'voice_rate': dlg.voice_rate
                        , 'voice_id': dlg.vid
                        , 'book_label': dlg.book_label
                        , 'container_root': dlg.container.root
                        , 'dest_dir': dlg.dest_dir
                        }

            # loop around selected files to record to MP3. Use calibre jobs system
            QueueProgressDialog(self.gui, dlg.payload, self._queue_job, djobmeta)

        
    def _queue_job(self, files_to_proc, bad_files):
        #For use when running as a background job with workers
        bad_files = []
        cpus = self.gui.job_manager.server.pool_size
        
        job = self.gui.job_manager.run_job(
                self.Dispatcher(self._jobs_complete),
                'arbitrary_n', 
                args=('calibre_plugins.tts_to_mp3_plugin.jobs',
                    'do_book_action_worker', 
                    (files_to_proc, bad_files, cpus)), 
                description= '%s:%s' % (PLUGIN_NAME, self.book_label))
                
        self.gui.status_bar.show_message('{0} for {1} file(s)'.format(PLUGIN_CAPTION, len(files_to_proc)))

    def _jobs_complete(self, job):
        if job.failed:
            self.gui.job_exception(job, dialog_title='Failed to run %s'%PLUGIN_NAME)
            return
            
        good_files, bad_files, det_msg = get_job_details(job)
        self.gui.status_bar.show_message('{0} jobs completed'.format(job.description), 3000)
        
        if bad_files:
            x, x, x, book_label = bad_files[0]
            msg = '<div>%s</div>' % book_label
            msg += '<p>%d MP3(s) could not be created.</p>' % len(bad_files)
            msg += '<p>Click "Show details" to see problem files.</p>'
            p = ErrorNotification(
                job.html_details, 
                job.description,
                '%s: Errors' % PLUGIN_NAME,
                msg, 
                det_msg=det_msg, 
                show_copy_button=True, 
                parent=self.gui)
            p.show()
        else:
            jobicon = find_icon('images/plugin_icon.png')
            x, x, x, x, book_label, mp3_dir, container_root, dest_dir = good_files[0]
            msg = '\n<div>%s</div>' % book_label
            popup_title = 'Audiobook MP3s created: %d' % len(good_files)
            elapsed = job.duration
            
            total_words = sum([wordcount for (pad_track, name, restext, wordcount, book_label, mp3_dir, container_root, dest_dir) in good_files])
            wpm = (60.0 * total_words / elapsed) if elapsed else 0.0
            footer = 'Recorded: {0} words @ {1:.0f} wpm'.format(total_words, wpm)
            msg += '\n<div>%s</div>' % footer
            
            #clean up calibre temp for this job
            shutil.rmtree(container_root, ignore_errors=True)
            shutil.rmtree(dest_dir, ignore_errors=True)

            self.gui.proceed_question(
                self._dummy_check_proceed, # callback, called with payload if user asks to proceed
                mp3_dir,       # payload, Arbitrary object, passed to callback/alt callback
                job.html_details,   # html_log, An HTML or plain text log
                job.description,    # log viewer title
                popup_title,        # title for this notification popup
                msg,                # msg to display
                action_callback=self._open_mp3_dir,         # instead of main callback
                action_label='Open MP&3 dir',               # label for alt action button
                action_icon=QIcon(I('document_open.png')),  # icon for alt action button
                focus_action=True,
                show_ok=True,       # instead of Yes/No buttons
                icon=jobicon,
                show_copy_button=True
                )

    def _open_mp3_dir(self, dir):
        open_local_file(dir)
        
    def _dummy_check_proceed(self, dummyarg):
        # dummy callback. This plugin does not update the calibre library
        pass
