from dataclasses import dataclass, field


@dataclass(slots=True)
class FileItem:
    name: str
    is_folder: bool = False
    children: list["FileItem"] = field(default_factory=list)
    checked: bool = True
    path: str | None = None


def mock_file_tree(source_name: str = "Документация проект.zip") -> FileItem:
    return FileItem(source_name, True, [
        FileItem("技术文档", True, [
            FileItem("第一章 简介", True, [
                FileItem("系统概述.pdf"), FileItem("安装说明.docx"),
            ]),
            FileItem("第二章 使用指南", True, [
                FileItem("启动车辆.pdf"), FileItem("配置参考.docx"), FileItem("readme.txt"),
            ]),
        ]),
        FileItem("localization.json"), FileItem("terms.xml"), FileItem("notes.md"),
        FileItem("license.txt"), FileItem("manifest.json"),
    ])
