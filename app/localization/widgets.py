"""Qt presentation adapters retain source labels for live locale changes.

Canonical combo values stay unchanged. No editor contents or document text is
translated; only app-owned labels, titles, tooltips and placeholders are bound.
"""
from PySide6 import QtWidgets as W
from . import localization, tr


class Localized:
    def __init__(self,*args,**kwargs):
        self._ui_sources = {}
        super().__init__(*args,**kwargs)
        localization.widgets.add(self)
        for getter,setter in (('text','setText'),('windowTitle','setWindowTitle'),
                              ('toolTip','setToolTip'),('accessibleName','setAccessibleName'),
                              ('placeholderText','setPlaceholderText')):
            if (hasattr(self,getter) and not isinstance(self,(W.QTextEdit,W.QLineEdit))) or getter=='placeholderText':
                if hasattr(self,getter):
                    value = getattr(self,getter)()
                    if isinstance(value,str) and value:
                        self._localized(setter,value)

    def _localized(self, method, value):
        self._ui_sources[method] = value
        getattr(super(),method)(tr(value))

    def setText(self,value): self._localized('setText',value)
    def setWindowTitle(self,value): self._localized('setWindowTitle',value)
    def setToolTip(self,value): self._localized('setToolTip',value)
    def setAccessibleName(self,value): self._localized('setAccessibleName',value)
    def setPlaceholderText(self,value): self._localized('setPlaceholderText',value)

    def retranslate(self):
        for method,source in self._ui_sources.items():
            getattr(super(),method)(tr(source))


class QLabel(Localized,W.QLabel): pass
class QPushButton(Localized,W.QPushButton): pass
class QCheckBox(Localized,W.QCheckBox): pass
class QRadioButton(Localized,W.QRadioButton): pass
class QToolButton(Localized,W.QToolButton): pass
class QDialog(Localized,W.QDialog): pass
class QMainWindow(Localized,W.QMainWindow): pass
class QTextEdit(Localized,W.QTextEdit):
    # Text editors contain user content, never UI messages.
    def setText(self,value): W.QTextEdit.setText(self,value)


class QTextBrowser(Localized,W.QTextBrowser):
    """Translate UI-only rich content, explicitly opt out for lexical examples."""
    def setHtml(self,value):
        if self.objectName() == 'licenseBrowser':
            self._localized('setHtml',value)
        else:
            self._ui_sources.pop('setPlainText',None)
            super().setHtml(value)
    def setPlainText(self,value):
        # Used for app-owned loading statuses; data uses setHtml without translation.
        self._localized('setPlainText',value)


class QComboBox(Localized,W.QComboBox):
    def __init__(self,*a,**kw):
        self._items=[]
        super().__init__(*a,**kw)

    def addItem(self,*args):
        args=list(args); position=0 if isinstance(args[0],str) else 1
        self._items.append(args[position]); args[position]=tr(args[position])
        super().addItem(*args)

    def addItems(self,items):
        for item in items:self.addItem(item)

    def setItemText(self,index,text):
        self._items[index]=text
        super().setItemText(index,tr(text))

    def currentText(self):
        i=self.currentIndex()
        return self._items[i] if 0<=i<len(self._items) else super().currentText()

    def setCurrentText(self,text):
        if text in self._items:self.setCurrentIndex(self._items.index(text))
        else:super().setCurrentText(text)

    def findText(self,text,*args):
        return self._items.index(text) if text in self._items else super().findText(text,*args)

    def retranslate(self):
        super().retranslate()
        blocked=self.blockSignals(True)
        try:
            for i,text in enumerate(self._items):W.QComboBox.setItemText(self,i,tr(text))
        finally:self.blockSignals(blocked)


class QFormLayout(W.QFormLayout):
    def addRow(self,*args):
        if args and isinstance(args[0],str):args=(QLabel(args[0]),*args[1:])
        super().addRow(*args)


class QListWidget(Localized,W.QListWidget):
    def __init__(self,*a,**kw):
        self._labels=[]
        super().__init__(*a,**kw)
    def addItems(self,items):
        self._labels.extend(items)
        super().addItems([tr(x) for x in items])
    def retranslate(self):
        super().retranslate()
        for i,text in enumerate(self._labels):self.item(i).setText(tr(text))


class QTabWidget(Localized,W.QTabWidget):
    def __init__(self,*a,**kw):
        self._labels=[]
        super().__init__(*a,**kw)
    def addTab(self,widget,text):
        self._labels.append(text)
        return super().addTab(widget,tr(text))
    def retranslate(self):
        super().retranslate()
        for i,text in enumerate(self._labels):self.setTabText(i,tr(text))


class QMenu(Localized,W.QMenu):
    def __init__(self,*a,**kw):
        self._actions=[]
        super().__init__(*a,**kw)
    def addAction(self,*args):
        args=list(args); index=0 if isinstance(args[0],str) else 1
        source=args[index];args[index]=tr(source)
        action=super().addAction(*args)
        self._actions.append((action,source))
        return action
    def retranslate(self):
        super().retranslate()
        for action,source in self._actions:action.setText(tr(source))


class QMessageBox(Localized,W.QMessageBox):
    def addButton(self,text,role):
        if isinstance(text,str):
            button=QPushButton(text)
            super().addButton(button,role)
            return button
        return super().addButton(text,role)
    @staticmethod
    def information(parent,title,text):
        return W.QMessageBox.information(parent,tr(title),tr(text))

    @staticmethod
    def question(parent, title, text, buttons, default_button):
        if buttons != W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No:
            return W.QMessageBox.question(parent, tr(title), tr(text), buttons, default_button)
        dialog = QMessageBox(parent)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        yes = dialog.addButton('Да', W.QMessageBox.ButtonRole.YesRole)
        no = dialog.addButton('Нет', W.QMessageBox.ButtonRole.NoRole)
        dialog.setDefaultButton(yes if default_button == W.QMessageBox.StandardButton.Yes else no)
        dialog.exec()
        result = W.QMessageBox.StandardButton.Yes if dialog.clickedButton() is yes else W.QMessageBox.StandardButton.No
        dialog.deleteLater()
        return result


class QFileDialog(W.QFileDialog):
    @staticmethod
    def getExistingDirectory(parent,caption,*args,**kw):
        return W.QFileDialog.getExistingDirectory(parent,tr(caption),*args,**kw)
    @staticmethod
    def getOpenFileNames(parent,caption,*args,**kw):
        args=list(args)
        if len(args)>1:args[1]=tr(args[1])
        return W.QFileDialog.getOpenFileNames(parent,tr(caption),*args,**kw)
