import configparser
import fnmatch
import getopt
import os
import sys
import time
import zipfile
import dropbox
import plist_utils
import http.client as http_client

#http_client.HTTPConnection.debuglevel = 1


HELP_MESSAGE = '사용법: main.py -i <업로드 파일> -o <DropBox 업로드 대상 폴더>'
HELP_MESSAGE_FULL = 'Usage: main.py -i <업로드 파일> -o <DropBox 업로드 대상 폴더>\n\
    Example: main.py -i /Users/user/AdHocFile.ipa -o /AdHocs/TestAdHoc'

PLIST_CONTENT_TEMPLATE = '<?xml version="1.0" encoding="UTF-8"?>\n\
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n\
<plist version="1.0">\n\
<dict>\n\
    <key>items</key>\n\
    <array>\n\
        <dict>\n\
            <key>assets</key>\n\
            <array>\n\
                <dict>\n\
                    <key>kind</key>\n\
                    <string>software-package</string>\n\
                    <key>url</key>\n\
                    <string>{key_url}</string>\n\
                </dict>\n\
            </array>\n\
            <key>metadata</key>\n\
            <dict>\n\
                <key>bundle-identifier</key>\n\
                <string>{key_bundle_identifier}</string>\n\
                <key>bundle-version</key>\n\
                <string>{key_bundle_version}</string>\n\
                <key>kind</key>\n\
                <string>software</string>\n\
                <key>title</key>\n\
                <string>{key_title}</string>\n\
            </dict>\n\
        </dict>\n\
    </array>\n\
</dict>\n\
</plist>'

DOWNLOAD_LINK_TEMPLATE_IOS = "itms-services://?action=download-manifest&url={key_plist_url}"

def analyse_ipa(ipa_file):
    with zipfile.ZipFile(ipa_file, "r") as ipa:
        ipa_info = {}
        files = ipa.namelist()
        info_plist = fnmatch.filter(files, "Payload/*.app/Info.plist")[0]
        info_plist_bin = ipa.read(info_plist)
        try:
            info = plist_utils.read_plist_from_string(info_plist_bin)
            ipa_info = info
        except:
            pass
        ipa.close()
        return ipa_info


def generate_plist_content_string_for_dropbox(ipa_file_path, ipa_url, ios8_suffix=None):
    ipa_info = analyse_ipa(ipa_file_path)
    if ipa_info is None:
        return None

    app_name = (
        ipa_info["CFBundleDisplayName"]
        if "CFBundleDisplayName" in ipa_info
        else ipa_info["CFBundleName"]
    )
    bundle_version = ipa_info["CFBundleVersion"]
    bundle_identifier = ipa_info["CFBundleIdentifier"]

    return PLIST_CONTENT_TEMPLATE.format(key_url=ipa_url, key_bundle_identifier=bundle_identifier, key_bundle_version=bundle_version, key_title=app_name).encode('utf-8')


def upload_and_share_file(dbx, dropbox_path, file_or_text_content):
    print('파일을 DropBox에 업로드 합니다. 업로드 위치: ' + dropbox_path)
    dbx.files_upload(file_or_text_content, dropbox_path)
    print('파일 업로드 완료')

    print('공유 링크를 생성중입니다...')
    shared_url = dbx.sharing_create_shared_link(dropbox_path)
    from urllib.parse import urlparse
    parsed_url = urlparse(shared_url.url)
    parsed_url = parsed_url._replace(netloc='dl.dropboxusercontent.com')
    parsed_url = parsed_url._replace(query=None)
    from urllib.parse import urlunparse

    shared_url_str = urlunparse(parsed_url)
    print('공유 링크 생성 완료. 링크: ' + shared_url_str)

    return shared_url_str


def upload_ipa_and_plist_files(ipa_local_path, output_dropbox_dir):
    appToken = None
    config_filename = 'deploy_config.ini'
    try:
        config = configparser.ConfigParser()
        config.read(config_filename)
        appToken = config['Dropbox authorization']['AppToken']
    except Exception:
        pass
    if appToken is None:
        print('설정 파일을 읽을 수 없습니다. >> ' + config_filename)
        exit(1)

    base_filename = os.path.basename(ipa_local_path)
    base_filename, ipa_extension = os.path.splitext(base_filename)
    if not '.ipa' == ipa_extension:
        print('파일 확장자가 ipa가 아닙니다. >> ', ipa_extension)
        exit(1)

    dbx = dropbox.Dropbox(appToken)
    try:
        with open(ipa_local_path, mode='rb') as f:
            ipa_dropbox_path = os.path.join(output_dropbox_dir, base_filename + '.ipa')
            ipa_dropbox_url = upload_and_share_file(dbx, ipa_dropbox_path, f.read())

            plist_dropbox_path = os.path.join(output_dropbox_dir, base_filename + '.plist')
            plist_content = generate_plist_content_string_for_dropbox(ipa_local_path, ipa_dropbox_url)
            plist_dropbox_url = upload_and_share_file(dbx, plist_dropbox_path, plist_content)

            download_link_ios = DOWNLOAD_LINK_TEMPLATE_IOS.format(key_plist_url=plist_dropbox_url)

            print('\nDropbox 배포 완료.')
            print('생성된 최종 주소\n' + download_link_ios)

    except Exception as err:
        print("파일 업로드 중 오류가 발생했습니다 >> ", err)
        exit(1)


def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hi:o:")
    except getopt.GetoptError:
        print(HELP_MESSAGE)
        sys.exit(2)

    ipa_local_path = None
    output_dropbox_dir = None
    for opt, arg in opts:
        if opt == '-h':
            print(HELP_MESSAGE_FULL)
            sys.exit()

        if opt == "-i":
            ipa_local_path = arg
            continue

        if opt == "-o":
            output_dropbox_dir = arg

    if ipa_local_path is None or output_dropbox_dir is None:
        print(HELP_MESSAGE)
        sys.exit(2)

    upload_ipa_and_plist_files(ipa_local_path, output_dropbox_dir)


if __name__ == '__main__':
    main()
