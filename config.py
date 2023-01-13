try:
    from qt.core import (
        Qt, QWidget, QGridLayout, QLabel, QComboBox, QCheckBox,
        QHBoxLayout, QVBoxLayout, QRadioButton, QSpinBox, QGroupBox, QLineEdit,
        QPushButton)
except ImportError:
    from PyQt5.Qt import (
        Qt, QWidget, QGridLayout, QLabel, QComboBox, QCheckBox,
        QHBoxLayout, QVBoxLayout, QRadioButton, QSpinBox, QGroupBox, QLineEdit,
        QPushButton)
        
# This is where all preferences for this plugin will be stored
# Remember that this plugin name is also
# in a global namespace, so make it as unique as possible.
# You should always prefix your config file name with plugins/,
# so as to ensure you dont accidentally clobber a calibre config file
# Set defaults

from calibre.utils.config import JSONConfig
from calibre_extensions.winsapi import ISpVoice

from calibre_plugins.tts_to_mp3_plugin.utils import get_sorted_voicedescs

prefs = JSONConfig('plugins/ebook2audiobook')

#sapi = ISpVoice()
prefs.defaults['voice_name'] = None
prefs.defaults['voice_rate'] = 0
prefs.defaults['img_alt_show'] = False
prefs.defaults['img_alt_prefix'] = 'Image'
prefs.defaults['embed_cover_thumbnail'] = True

class ConfigWidget(QWidget):

    def __init__(self):
        QWidget.__init__(self)
        
        self.l = QVBoxLayout()
        self.setLayout(self.l)
        
        gpcover = QGroupBox('Cover thumbnail:')
        laycover = QHBoxLayout()
        gpcover.setLayout(laycover)
        
        self.embedcoverCheckbox = QCheckBox('Embed in each MP3?')
        self.embedcoverCheckbox.setMinimumWidth(200)
        self.embedcoverCheckbox.setMaximumWidth(200)
        self.embedcoverCheckbox.setChecked(prefs['embed_cover_thumbnail'])
        
        helpembedcoverLabel = QLabel("If UNCHECKED a cover thumbnail (cover.jpg) will be copied to the MP3 directory.")
        helpembedcoverLabel.setWordWrap(True)
        helpembedcoverLabel.setMinimumWidth(350)
        helpembedcoverLabel.setMaximumWidth(350)
        
        laycover.addWidget(self.embedcoverCheckbox)
        laycover.addWidget(helpembedcoverLabel)
        
        gpimgalt = QGroupBox('Image alternate text: (experimental)')
        layimgalt = QGridLayout()
        gpimgalt.setLayout(layimgalt)
        
        self.imgaltshowCheckbox = QCheckBox('Speak <img> "alt" text?')
        self.imgaltshowCheckbox.setChecked(prefs['img_alt_show'])
        self.imgaltshowCheckbox.setMinimumWidth(200)
        self.imgaltshowCheckbox.setMaximumWidth(200)

        helpimgaltshowLabel = QLabel('<p>If CHECKED any text contained in the "alt" attribute of an &lt;img&gt; tag will be included in the spoken text.</p><p>e.g. &lt;img alt="Map of Westeros" src="images/map.jpg"/&gt;<br/></p>')
        helpimgaltshowLabel.setWordWrap(True)
        helpimgaltshowLabel.setMinimumWidth(350)
        helpimgaltshowLabel.setMaximumWidth(350)
        
        prefixs = set(['<none>', 'Image'])
        prefix = prefs['img_alt_prefix']
        if len(prefix) == 0:
            prefix = '<none>'
        else:
            prefixs.add(prefix)
        
        self.imgaltprefixCombo = QComboBox()
        self.imgaltprefixCombo.setMinimumWidth(200)
        self.imgaltprefixCombo.setMaximumWidth(200)
        self.imgaltprefixCombo.setEditable(True)
        self.imgaltprefixCombo.addItems(sorted(prefixs))
        self.imgaltprefixCombo.setCurrentText(prefix)
        
        helpimgaltprefixLabel = QLabel('If the above box is CHECKED this text will be spoken as a prefix to the "alt" text.')
        helpimgaltprefixLabel.setWordWrap(True)
        helpimgaltprefixLabel.setMinimumWidth(350)
        helpimgaltprefixLabel.setMaximumWidth(350)
        
        layimgalt.addWidget(self.imgaltshowCheckbox, 0, 0)
        layimgalt.addWidget(helpimgaltshowLabel, 0, 1)
        layimgalt.addWidget(self.imgaltprefixCombo, 1, 0)
        layimgalt.addWidget(helpimgaltprefixLabel, 1, 1)
        
        gpvoice = QGroupBox('Default Voice and Speech Rate:')
        layvoice = QGridLayout()
        gpvoice.setLayout(layvoice)
        
        self.voiceCombo = QComboBox()
        self.voiceCombo.setMinimumWidth(350)
        self.voiceCombo.setMaximumWidth(350)
        
        voiceLabel = QLabel('&Voice:')
        voiceLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        voiceLabel.setBuddy(self.voiceCombo)
        voiceLabel.setMinimumWidth(200)
        voiceLabel.setMaximumWidth(200)
        
        # search Windows for available Voices
        self.spVoice = ISpVoice()
        all_descs = get_sorted_voicedescs(self.spVoice)
        self.voiceCombo.addItems(all_descs)
        
        if prefs['voice_name'] in all_descs:
            self.voiceCombo.setCurrentText(prefs['voice_name'])
        else:
            self.voiceCombo.setCurrentIndex(0)
        
        self.rateSpin = QSpinBox()
        self.rateSpin.setRange(-10, 10)
        self.rateSpin.setToolTip('Range (-10, 10)')
        self.rateSpin.setSingleStep(1)
        
        rateLabel = QLabel('Speech &Rate:')
        rateLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rateLabel.setBuddy(self.rateSpin)
        rateLabel.setMinimumWidth(200)
        rateLabel.setMaximumWidth(200)
        
        self.rateSpin.setValue(prefs['voice_rate'])
        
        layvoice.addWidget(voiceLabel, 0, 0)
        layvoice.addWidget(self.voiceCombo, 0, 1, 1, 3)
        layvoice.addWidget(rateLabel, 1, 0)
        layvoice.addWidget(self.rateSpin, 1, 1)
        
        self.l.addWidget(gpvoice)
        self.l.addWidget(gpcover)
        self.l.addWidget(gpimgalt)
        
        self.imgaltshowCheckbox.toggled.connect(self.imgaltshowCheckbox_toggled)
        
        self.imgaltshowCheckbox_toggled(self.imgaltshowCheckbox.isChecked())
        
    def imgaltshowCheckbox_toggled(self, bool):    
        self.imgaltprefixCombo.setEnabled(bool)
        
    def save_settings(self):
        prefs['embed_cover_thumbnail'] = self.embedcoverCheckbox.isChecked()
        prefs['img_alt_show'] = self.imgaltshowCheckbox.isChecked()
        prefix = self.imgaltprefixCombo.currentText().strip()
        if not prefix or '<none>' in prefix:
            prefs['img_alt_prefix'] = ''
        elif prefix.startswith('<'):
            prefs['img_alt_prefix'] = ''
        else:
            prefs['img_alt_prefix'] = prefix
            
        prefs['voice_name'] = self.voiceCombo.currentText()
        prefs['voice_rate'] = self.rateSpin.value()
                          
if __name__ == "__main__":
    # called from Op sys
    import sys
    
    try:
        from qt.core import QApplication
    except ImportError:
        from PyQt5.Qt import QApplication
        
    app = QApplication(sys.argv)
    win = ConfigWidget()
    win.show()
    app.exec()
