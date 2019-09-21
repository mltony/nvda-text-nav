#A part of the TextNav addon for NVDA
#Copyright (C) 2018 Tony Malykh
#This file is covered by the GNU General Public License.
#See the file COPYING.txt for more details.

import addonHandler
import api
import bisect
import config
import controlTypes
import ctypes
import globalPluginHandler
import gui
import NVDAHelper
from NVDAObjects.window import winword
import operator
import re 
from scriptHandler import script
import speech
import struct
import textInfos
import tones
import ui
import wx

def myAssert(condition):
    if not condition:
        raise RuntimeError("Assertion failed")

def createMenu():
    def _popupMenu(evt):
        gui.mainFrame._popupSettingsDialog(SettingsDialog)
    prefsMenuItem  = gui.mainFrame.sysTrayIcon.preferencesMenu.Append(wx.ID_ANY, _("TextNav..."))
    gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, _popupMenu, prefsMenuItem)

def initConfiguration():
    confspec = {
        "crackleVolume" : "integer( default=25, min=0, max=100)",
        "noNextTextChimeVolume" : "integer( default=50, min=0, max=100)",
        "noNextTextMessage" : "boolean( default=False)",
        "speakFormatted" : "boolean( default=True)",
        "applicationsBlacklist" : "string( default='audacity,excel')",
    }
    config.conf.spec["textnav"] = confspec
    
def getConfig(key):
    value = config.conf["textnav"][key]
    return value
    
addonHandler.initTranslation()
initConfiguration()
createMenu()


class SettingsDialog(gui.SettingsDialog):
    # Translators: Title for the settings dialog
    title = _("TextNav settings")

    def __init__(self, *args, **kwargs):
        super(SettingsDialog, self).__init__(*args, **kwargs)

    def makeSettings(self, settingsSizer):
        sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
      # crackleVolumeSlider
        sizer=wx.BoxSizer(wx.HORIZONTAL)
        # Translators: volume of crackling slider
        label=wx.StaticText(self,wx.ID_ANY,label=_("Crackling volume"))
        slider=wx.Slider(self, wx.NewId(), minValue=0,maxValue=100)
        slider.SetValue(getConfig("crackleVolume"))
        sizer.Add(label)
        sizer.Add(slider)
        settingsSizer.Add(sizer)
        self.crackleVolumeSlider = slider

      # noNextTextChimeVolumeSlider
        sizer=wx.BoxSizer(wx.HORIZONTAL)
        # Translators: End of document chime volume
        label=wx.StaticText(self,wx.ID_ANY,label=_("Volume of chime when no more sentences available"))
        slider=wx.Slider(self, wx.NewId(), minValue=0,maxValue=100)
        slider.SetValue(getConfig("noNextTextChimeVolume"))
        sizer.Add(label)
        sizer.Add(slider)
        settingsSizer.Add(sizer)
        self.noNextTextChimeVolumeSlider = slider
        
      # Checkboxes
        # Translators: Checkbox that controls spoken message when no next or previous text paragraph is available in the document
        label = _("Speak message when no next paragraph containing text available in the document")
        self.noNextTextMessageCheckbox = sHelper.addItem(wx.CheckBox(self, label=label))
        self.noNextTextMessageCheckbox.Value = getConfig("noNextTextMessage")
        # Translators: speak formatted text checkbox
        label = _("Speak formatted text")
        self.speakFormattedCheckbox = sHelper.addItem(wx.CheckBox(self, label=label))
        self.speakFormattedCheckbox.Value = getConfig("speakFormatted")
      # applicationsBlacklist edit
        # Translators: Label for blacklisted applications edit box
        self.applicationsBlacklistEdit = gui.guiHelper.LabeledControlHelper(self, _("Disable TextNav in applications (comma-separated list)"), wx.TextCtrl).control
        self.applicationsBlacklistEdit.Value = getConfig("applicationsBlacklist")
        
    def onOk(self, evt):
        config.conf["textnav"]["crackleVolume"] = self.crackleVolumeSlider.Value
        config.conf["textnav"]["noNextTextChimeVolume"] = self.noNextTextChimeVolumeSlider.Value
        config.conf["textnav"]["noNextTextMessage"] = self.noNextTextMessageCheckbox.Value
        config.conf["textnav"]["speakFormatted"] = self.speakFormattedCheckbox.Value
        config.conf["textnav"]["applicationsBlacklist"] = self.applicationsBlacklistEdit.Value
        super(SettingsDialog, self).onOk(evt)



class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = _("TextNav")
    
    def re_grp(s):
        """Wraps a string with a non-capturing group for use in regular expressions."""
        return "(?:%s)" % s        
    
    SENTENCE_BREAKERS = ".?!"
    CHINESE_SENTENCE_BREAKERS = ("["
        + u"\u3002" # Chinese full stop
        + u"\uFF01" # Chinese exclamation mark
        + u"\uFF1F" # Chinese question mark
        + "]+") 

    SKIPPABLE_PUNCTUATION = (
        u'")'
        + u"\u201D" # Right double quotation mark
        )  
    WIKIPEDIA_REFERENCE = re_grp("\\[[\\w\\s]+\\]")
    SENTENCE_END_REGEX = u"[{br}]+[{skip}]*{wiki}*\\s+".format(
        br=SENTENCE_BREAKERS ,
        wiki=WIKIPEDIA_REFERENCE,
        skip = SKIPPABLE_PUNCTUATION)
    SENTENCE_END_REGEX = re_grp("^|" + SENTENCE_END_REGEX + "|" + CHINESE_SENTENCE_BREAKERS + "|\\s*$")
    SENTENCE_END_REGEX  = re.compile(SENTENCE_END_REGEX , re.UNICODE)
    
    def splitParagraphIntoSentences(self, text, regex=None):
        if regex is None:
            regex = self.SENTENCE_END_REGEX
        result = [m.end() for m in regex.finditer(text)]
        # Sometimes the last position in the text will be matched twice, so filter duplicates.
        result = sorted(list(set(result)))
        return result

    @script(description='Move to next  paragraph containing text.', gestures=['kb:Alt+Shift+DownArrow'])
    def script_nextText(self, gesture):
        if self.maybePassThrough(gesture):
            return
        # Translators: error message when no next paragraph with text is available in the document
        errorMsg = _("No next paragraph with text")
        self.moveToText(gesture, 1, errorMsg)

    @script(description='Move to previous  paragraph containing text.', gestures=['kb:Alt+Shift+UpArrow'])
    def script_previousText(self, gesture):
        if self.maybePassThrough(gesture):
            return
        # Translators: error message when no previous paragraph with text is available in the document
        errorMsg = _("No previous paragraph with text")
        self.moveToText(gesture, -1, errorMsg)

    def maybePassThrough(self, gesture):
        focus = api.getFocusObject()
        appName = focus.appModule.appName
        if appName.lower() in getConfig("applicationsBlacklist").lower().strip().split(","):
            gesture.send()
            return True
        return False

    def moveToText(self, gesture, increment, errorMsg="Error"):
        focus = api.getFocusObject()
        if hasattr(focus, "treeInterceptor") and hasattr(focus.treeInterceptor, "makeTextInfo"):
            focus = focus.treeInterceptor
        textInfo = focus.makeTextInfo(textInfos.POSITION_CARET)
        distance = 0
        while True:
            textInfo.collapse()
            result =textInfo.move(textInfos.UNIT_PARAGRAPH, increment)
            if result == 0:
                volume = getConfig("noNextTextChimeVolume")
                self.fancyBeep("HF", 100, volume, volume)
                if getConfig("noNextTextMessage"):
                    ui.message(errorMsg)
                return
            distance += 1
            if distance==1000:
                # Translators: error message if for some reason TextNav enters infinite loop
                ui.message(_("TextNav error: Infinite loop"))
                return
            textInfo.expand(textInfos.UNIT_PARAGRAPH)
            text = textInfo.text
            
            # Small hack: our regex always matches the end of the string, since any sentence must end at the end of the paragraph.
            # In this case, however, we need to figure out if the sentence really ends with a full stop or other sentence breaker at the end.
            # So we add a random word in the end of the string and see if there is any other sentence boundaries besides the beginning and the end of the string.
            text2 = text + " FinalWord"
            boundaries = self.splitParagraphIntoSentences(text2)
            if len(boundaries) >= 3:
                textInfo.updateCaret()
                self.simpleCrackle(distance, getConfig("crackleVolume"))
                if getConfig("speakFormatted"):
                    speech.speakTextInfo(textInfo, reason=controlTypes.REASON_CARET)
                else:
                    speech.speakText(text)
                break

    NOTES = "A,B,H,C,C#,D,D#,E,F,F#,G,G#".split(",")
    NOTE_RE = re.compile("[A-H][#]?")
    BASE_FREQ = 220 
    def getChordFrequencies(self, chord):
        myAssert(len(self.NOTES) == 12)
        prev = -1
        result = []
        for m in self.NOTE_RE.finditer(chord):
            s = m.group()
            i =self.NOTES.index(s) 
            while i < prev:
                i += 12
            result.append(int(self.BASE_FREQ * (2 ** (i / 12.0))))
            prev = i
        return result            
    
    def fancyBeep(self, chord, length, left=10, right=10):
        beepLen = length 
        freqs = self.getChordFrequencies(chord)
        intSize = 8 # bytes
        bufSize = max([NVDAHelper.generateBeep(None,freq, beepLen, right, left) for freq in freqs])
        if bufSize % intSize != 0:
            bufSize += intSize
            bufSize -= (bufSize % intSize)
        tones.player.stop()
        bbs = []
        result = [0] * (bufSize//intSize)
        for freq in freqs:
            buf = ctypes.create_string_buffer(bufSize)
            NVDAHelper.generateBeep(buf, freq, beepLen, right, left)
            bytes = bytearray(buf)
            unpacked = struct.unpack("<%dQ" % (bufSize / intSize), bytes)
            result = map(operator.add, result, unpacked)
        maxInt = 1 << (8 * intSize)
        result = map(lambda x : x %maxInt, result)
        packed = struct.pack("<%dQ" % (bufSize / intSize), *result)
        tones.player.feed(packed)

    def uniformSample(self, a, m):
        n = len(a)
        if n <= m:
            return a
        # Here assume n > m
        result = []
        for i in range(0, m*n, n):
            result.append(a[i  / m])
        return result
    
    BASE_FREQ = speech.IDT_BASE_FREQUENCY
    def getPitch(self, indent):
        return self.BASE_FREQ*2**(indent/24.0) #24 quarter tones per octave.

    BEEP_LEN = 10 # millis
    PAUSE_LEN = 5 # millis
    MAX_CRACKLE_LEN = 400 # millis
    MAX_BEEP_COUNT = MAX_CRACKLE_LEN / (BEEP_LEN + PAUSE_LEN)
        
    def fancyCrackle(self, levels, volume):
        levels = self.uniformSample(levels, self.MAX_BEEP_COUNT )
        beepLen = self.BEEP_LEN 
        pauseLen = self.PAUSE_LEN
        pauseBufSize = NVDAHelper.generateBeep(None,self.BASE_FREQ,pauseLen,0, 0)
        beepBufSizes = [NVDAHelper.generateBeep(None,self.getPitch(l), beepLen, volume, volume) for l in levels]
        bufSize = sum(beepBufSizes) + len(levels) * pauseBufSize
        buf = ctypes.create_string_buffer(bufSize)
        bufPtr = 0
        for l in levels:
            bufPtr += NVDAHelper.generateBeep(
                ctypes.cast(ctypes.byref(buf, bufPtr), ctypes.POINTER(ctypes.c_char)), 
                self.getPitch(l), beepLen, volume, volume)
            bufPtr += pauseBufSize # add a short pause
        tones.player.stop()
        tones.player.feed(buf.raw)

    def simpleCrackle(self, n, volume):
        return self.fancyCrackle([0] * n, volume)

