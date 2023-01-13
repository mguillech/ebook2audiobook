import os, shutil, re
from polyglot.builtins import unicode_type

try:
    from qt.core import (
        QDialog, Qt, QVBoxLayout, QHBoxLayout, QGridLayout, 
        QGroupBox, QFrame, QSplitter, QDialogButtonBox, QIcon, QTimer,
        QLabel, QTextBrowser, QPushButton, QTextEdit,
        QComboBox, QSpinBox, QRadioButton,
        QTableWidget, QTableWidgetItem, QAbstractItemView, QVariant)
except ImportError:
    from PyQt5.Qt import (
        QDialog, Qt, QVBoxLayout, QHBoxLayout, QGridLayout, 
        QGroupBox, QFrame, QSplitter, QDialogButtonBox, QIcon, QTimer,
        QLabel, QTextBrowser, QPushButton, QTextEdit,
        QComboBox, QSpinBox, QRadioButton,
        QTableWidget, QTableWidgetItem, QAbstractItemView, QVariant)

from calibre.devices.usbms.driver import debug_print
from calibre_extensions.winsapi import ISpVoice

#import from this plugin
from calibre_plugins.tts_to_mp3_plugin import PLUGIN_NAME    
from calibre_plugins.tts_to_mp3_plugin.common_utils import find_icon
from calibre_plugins.tts_to_mp3_plugin.utils import get_voiceid_from_desc, get_sorted_voicedescs

class SpeakFlags():
    SVSFDefault                   =0          # from enum SpeechVoiceSpeakFlags
    SVSFIsFilename                =4          # from enum SpeechVoiceSpeakFlags
    SVSFIsNotXML                  =16         # from enum SpeechVoiceSpeakFlags
    SVSFIsXML                     =8          # from enum SpeechVoiceSpeakFlags
    SVSFNLPMask                   =64         # from enum SpeechVoiceSpeakFlags
    SVSFNLPSpeakPunc              =64         # from enum SpeechVoiceSpeakFlags
    SVSFParseAutodetect           =0          # from enum SpeechVoiceSpeakFlags
    SVSFParseMask                 =384        # from enum SpeechVoiceSpeakFlags
    SVSFParseSapi                 =128        # from enum SpeechVoiceSpeakFlags
    SVSFParseSsml                 =256        # from enum SpeechVoiceSpeakFlags
    SVSFPersistXML                =32         # from enum SpeechVoiceSpeakFlags
    SVSFPurgeBeforeSpeak          =2          # from enum SpeechVoiceSpeakFlags
    SVSFUnusedFlags               =-512       # from enum SpeechVoiceSpeakFlags
    SVSFVoiceMask                 =511        # from enum SpeechVoiceSpeakFlags
    SVSFlagsAsync                 =1          # from enum SpeechVoiceSpeakFlags


class SelNamesDlg(QDialog):
    ''' select ebook spine files to be recorded to WAV/MP3 '''
    
    def __init__(self, select_spines, spine_dict, name_text_map, vname, vrate, parent=None):
        QDialog.__init__(self, parent=parent)
        
        self.select_spines = select_spines
        self.all_spines = [d['name'] for d in spine_dict]
        self.name_text_map = name_text_map
        
        # init test voice to same as in main dialog
        self.vname = vname
        self.vrate = vrate
        self.vid = None
        
        self.testVoice = ISpVoice()
        self.isPlaying = False
        
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        
        gptable = QGroupBox('Select &Files:')
        laytable = QHBoxLayout()
        gptable.setLayout(laytable)
        
        self.selnameTable = SelNamesTableWidget(self)
        laytable.addWidget(self.selnameTable)
        
        gpvoice = QGroupBox('&Voice Tester:')
        layvoice = QGridLayout()
        gpvoice.setLayout(layvoice)
        
        self.testvoiceCombo = QComboBox()
        
        self.testrateSpin = QSpinBox()
        self.testrateSpin.setToolTip('Range (-10, 10)')
        self.testrateSpin.setRange(-10, 10)
        self.testrateSpin.setSingleStep(1)
        
        rateLabel = QLabel('Speech &Rate:')
        rateLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rateLabel.setBuddy(self.testrateSpin)
        
        layvoice.addWidget(self.testvoiceCombo, 0, 0, 1, 3)
        layvoice.addWidget(rateLabel, 1, 1)
        layvoice.addWidget(self.testrateSpin, 1, 2)
        
        self.playstopButton = QPushButton('x')
        self.playstopButton.setMaximumWidth(100)
        
        layvoice.addWidget(self.playstopButton, 2, 0)
        
        gpbrowser = QGroupBox('Book text:')
        gpbrowser.setToolTip('From first selected file')
        laybrowser = QVBoxLayout()
        gpbrowser.setLayout(laybrowser)
        
        self.browser = QTextBrowser()
        self.browser.setMinimumWidth(300)
        self.browser.setReadOnly(True)
        self.browser.setText('')
        laybrowser.addWidget(self.browser)
        
        gpbrowser2 = QGroupBox('... or enter your own sample text:')
        gpbrowser2.setToolTip('When using the Voice Tester, this text takes priority over the actual book text above')
        laybrowser2 = QGridLayout()
        gpbrowser2.setLayout(laybrowser2)
        
        self.usersampleTextedit = QTextEdit()
        self.usersampleTextedit.setReadOnly(False)
        clearusersampleButton = QPushButton('&Clear')
        clearusersampleButton.setMaximumWidth(100)
        
        laybrowser2.addWidget(clearusersampleButton, 0, 2)
        laybrowser2.addWidget(self.usersampleTextedit, 1, 0, 1, 3)
        
        column2 = QFrame()
        laycolumn2 = QVBoxLayout()
        column2.setLayout(laycolumn2)
        
        laycolumn2.addWidget(gpvoice)
        laycolumn2.addWidget(gpbrowser)
        laycolumn2.addWidget(gpbrowser2)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(gptable)
        splitter.addWidget(column2)
        
        layout = QVBoxLayout()
        layout.addWidget(splitter)
        layout.addWidget(self.buttonBox)
        self.setLayout(layout)
        
        # create connect signals/slots
        self.playstopButton.clicked.connect(self.play_or_stop)
        clearusersampleButton.clicked.connect(self.clearusersampleButton_clicked)
        
        self.testvoiceCombo.currentTextChanged.connect(self.testvoiceCombo_textChanged)
        self.testrateSpin.valueChanged.connect(self.testrateSpin_valueChanged)
        
        self.selnameTable.itemSelectionChanged.connect(self.selnameTable_itemSelectionChanged)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        
        self.setWindowTitle('{0}: Select HTML files to be recorded to MP3'.format(PLUGIN_NAME))
        
        # initialise data
        self.toggle_player_settings(True)
        
        all_descs = get_sorted_voicedescs(self.testVoice)
        self.testvoiceCombo.addItems(all_descs)
        
        self.testvoiceCombo.setCurrentText(vname)
        self.testrateSpin.setValue(vrate)
        
        self.selnameTable.populate_table([d for d in spine_dict])
        # restore previous selection
        for name in self.select_spines:
            self.selnameTable.set_as_selected(name)

    def testvoiceCombo_textChanged(self, text):
        self.vname = text
        self.vid = get_voiceid_from_desc(self.testVoice, text)
            
    def testrateSpin_valueChanged(self, int):
        self.vrate = int
        self.testVoice.set_current_rate(int)
        
    def clearusersampleButton_clicked(self):
        self.usersampleTextedit.setText('')
        
    def selnameTable_itemSelectionChanged(self):
        self.stop_speech()
        sel_names = self.selnameTable.get_selected_spine()
        if sel_names:
            # populate the text box to allow voice testing
            name0 = [name for name in self.all_spines if name in sel_names][0]
            booktext = self.name_text_map[name0].get('booktext', '')
            self.browser.setPlainText(booktext)
            
    def accept(self):
        self.select_spines = self.selnameTable.get_selected_spine()
        self.stop()
        QDialog.accept(self)
            
    def reject(self):
        self.stop()
        QDialog.reject(self)
            
    def toggle_player_settings(self, bool):
        self.testvoiceCombo.setEnabled(bool)
        self.isPlaying = not bool
        
        self.playstopButton.setText('&Play' if bool else 'S&top')
        icon = find_icon('images/play.png' if bool else 'images/stop.png')
        self.playstopButton.setIcon(icon)
            
    def play_or_stop(self):
        if self.isPlaying:
            self.stop_speech()
        else:
            self.start_speech()
        
    def start_speech(self):
        book_text = self.browser.toPlainText()
        user_text = self.usersampleTextedit.toPlainText().strip()
        saytext = user_text if user_text else book_text
        if saytext:
            self.play(saytext)
        
    def play(self, text):
        # initialise Voice
        self.testVoice = ISpVoice()
        self.testVoice.set_current_voice(self.vid)
        self.testVoice.set_current_rate(self.vrate)
        
        self.toggle_player_settings(False)
        self.testVoice.speak(text, SpeakFlags.SVSFlagsAsync)
        self.check_speaking_done()
            
    def stop_speech(self):
        self.stop()
        self.toggle_player_settings(True)
            
    def stop(self):
        self.testVoice.pause()

    def check_speaking_done(self):
       if self.testVoice.wait_until_done(10):
            #self.stop_speech()
            self.toggle_player_settings(True)
       else:
            QTimer.singleShot(10, self.check_speaking_done)
        
class SelNamesTableWidget(QTableWidget):
    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table(self, lines):
        # lines = {rownum: 'toc'=?, 'name'=?, 'sample'=?, 'wordcount'=?} 
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(lines))
        header_labels = ['HTML filename', 'Word count', 'ToC entry']
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().hide()
        
        self.lines={}
        for row, line in enumerate(lines):
            self.populate_table_row(row, line)
            self.lines[row] = line
            
        self.resizeColumnsToContents()
        self.horizontalHeader().setStretchLastSection(True)
        self.setMinimumColumnWidth(0, 200)
        self.setMinimumColumnWidth(1, 100)
        self.setMinimumColumnWidth(2, 200)
        self.setMinimumSize(600, 700)
        self.setSortingEnabled(False)

    def populate_table_row(self, row, line):
        # lines = {rownum: 'toc'=?, 'name'=?, 'wordcount'=?}
        toc = line['toc']
        name = line['name']
        words = line['wordcount']

        name_cell = ReadOnlyTableWidgetItem(name)
        name_cell.setToolTip(line['sample'])
        name_cell.setData(Qt.ItemDataRole.UserRole, QVariant(name_cell))
        self.setItem(row, 0, name_cell)
        
        words_str = str(words)
        words_cell = ReadOnlyTableWidgetItem(words_str)
        words_cell.setData(Qt.ItemDataRole.UserRole, QVariant(words_str))
        words_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter|Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, 1, words_cell)
        
        toc_cell = ReadOnlyTableWidgetItem(toc)
        toc_cell.setData(Qt.ItemDataRole.UserRole, QVariant(toc_cell))
        self.setItem(row, 2, toc_cell)
        
    def set_as_selected(self, name):
        for row in [r for r in self.lines if self.lines[r]['name'] == name]:
            for col in range(self.columnCount()):
                self.item(row, col).setSelected(True)
            
    def get_selected_spine(self):
        return [self.item(row.row(), 0).text() for row in self.selectionModel().selectedRows()]

        
class ReadOnlyTableWidgetItem(QTableWidgetItem):
    def __init__(self, text): 
        if text is None:
            text = ''
        QTableWidgetItem.__init__(self, text)
        self.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)

        
class EbookSelectFormat(QDialog):
    # select a single format if >1 suitable to be container-ised

    def __init__(self, gui, formats, msg, parent=None):
        QDialog.__init__(self, parent=parent)
        
        self.gui = gui
        self.formats = formats
        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        
        label = QLabel(msg)
        
        self.dradio = {}
        for k in self.formats:
            self.dradio[k] = QRadioButton(k)

        gpbox1 = QGroupBox('Formats available:')
        lay1 = QHBoxLayout()
        gpbox1.setLayout(lay1)
        
        for fmt in self.formats:
            lay1.addWidget(self.dradio[fmt])
            
        if 'EPUB' in self.formats:
            self.dradio['EPUB'].setChecked(True)
        else:
            self.dradio[self.formats[0]].setChecked(True)
        
        lay = QVBoxLayout()
        lay.addWidget(label)
        lay.addWidget(gpbox1)
        lay.addStretch()
        lay.addWidget(buttonBox)
        self.setLayout(lay)
        
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        
        self.setWindowTitle('{0}: Select format'.format(PLUGIN_NAME))
        
        icon = find_icon('images/plugin_icon.png')
        self.setWindowIcon(icon)
        
    @property
    def result(self):
        return [k for k in self.formats if self.dradio[k].isChecked()]
