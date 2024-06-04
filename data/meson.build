desktop_file = i18n.merge_file(
        input: 'com.github.molnarandris.texwriter.desktop.in',
       output: 'com.github.molnarandris.texwriter.desktop',
         type: 'desktop',
       po_dir: '../po',
      install: true,
  install_dir: get_option('datadir') / 'applications'
)

desktop_utils = find_program('desktop-file-validate', required: false)
if desktop_utils.found()
  test('Validate desktop file', desktop_utils, args: [desktop_file])
endif

appstream_file = i18n.merge_file(
        input: 'com.github.molnarandris.texwriter.metainfo.xml.in',
       output: 'com.github.molnarandris.texwriter.metainfo.xml',
       po_dir: '../po',
      install: true,
  install_dir: get_option('datadir') / 'metainfo'
)

appstreamcli = find_program('appstreamcli', required: false, disabler: true)
test('Validate appstream file', appstreamcli,
     args: ['validate', '--no-net', '--explain', appstream_file])

install_data('com.github.molnarandris.texwriter.gschema.xml',
  install_dir: get_option('datadir') / 'glib-2.0' / 'schemas'
)

compile_schemas = find_program('glib-compile-schemas', required: false, disabler: true)
test('Validate schema file',
     compile_schemas,
     args: ['--strict', '--dry-run', meson.current_source_dir()])

pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
gnome.compile_resources('texwriter',
  'texwriter.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

subdir('icons')
