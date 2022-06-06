"""The driver for this Zeek package template. See the documentation at

https://docs.zeek.org/projects/package-manager/en/stable/zkg.html#create
https://docs.zeek.org/projects/package-manager/en/stable/api/template.html

for details.
"""
from datetime import date
import os
import textwrap

import git

import zeekpkg.template # pylint: disable=import-error
import zeekpkg.uservar # pylint: disable=import-error

# pylint: disable=missing-docstring,no-self-use

TEMPLATE_API_VERSION = '1.0.0'

class Package(zeekpkg.template.Package):
    def contentdir(self):
        return 'package'

    def needed_user_vars(self):
        return ['name']

    def validate(self, tmpl):
        if not tmpl.lookup_param('name'):
            raise zeekpkg.template.InputError(
                'package requires a name')

        if not tmpl.lookup_param('name').isalnum():
            raise zeekpkg.template.InputError(
                'package name "{}" must be alphanumeric'
                .format(tmpl.lookup_param('name')))

        if tmpl.lookup_param('namespace') and not tmpl.lookup_param('namespace').isalnum():
            raise zeekpkg.template.InputError(
                'package namespace "{}" must be alphanumeric'
                .format(tmpl.lookup_param('namespace')))


class Plugin(zeekpkg.template.Feature):
    def contentdir(self):
        return 'plugin'

    def needed_user_vars(self):
        return ['namespace']

    def validate(self, tmpl):
        if not tmpl.lookup_param('ns'):
            raise zeekpkg.template.InputError(
                'plugins require a namespace')

        if not tmpl.lookup_param('ns').isalnum():
            raise zeekpkg.template.InputError(
                'package namespace "{}" must be alphanumeric'
                .format(tmpl.lookup_param('ns')))


class License(zeekpkg.template.Feature):
    def license_keys(self, tmpl):
        licdir = os.path.join(tmpl.templatedir(), self.contentdir())
        return sorted(os.listdir(licdir))

    def contentdir(self):
        return 'license-feature'

    def needed_user_vars(self):
        return ['author', 'license']

    def validate(self, tmpl):
        if not tmpl.lookup_param('author'):
            raise zeekpkg.template.InputError('license requires an author')
        if not tmpl.lookup_param('license'):
            raise zeekpkg.template.InputError('license requires a license type')
        if tmpl.lookup_param('license') not in self.license_keys(tmpl):
            types_str = ', '.join(self.license_keys(tmpl))
            raise zeekpkg.template.InputError('license type must be one of ' + types_str)

    def instantiate(self, tmpl):
        # We reimplement this to select a specific input file instead of a
        # folder walk -- we only need a single output for this feature.
        prefix = os.path.join(tmpl.templatedir(), self.contentdir())
        in_file = os.path.join(prefix, tmpl.lookup_param('license'))
        with open(in_file, 'rb') as hdl:
            out_content = self._replace(tmpl, hdl.read())
        self.instantiate_file(
            tmpl, os.path.join(prefix, tmpl.lookup_param('license')),
            '', 'COPYING', out_content)


class GithubCi(zeekpkg.template.Feature):
    def contentdir(self):
        return 'github-ci'


class SpicyAnalyzer(zeekpkg.template.Feature):
    """Feature for a Spicy-based analyzer."""

    def contentdir(self):
        return 'spicy-analyzer'

    def needed_user_vars(self):
        """Specify required user variables."""
        return ['name', 'namespace']

    def validate(self, tmpl):
        """Validate feature prerequisites."""
        for parameter in ['name', 'ns']:
            value = tmpl.lookup_param(parameter)
            if not value or len(value) == 0:
                raise zeekpkg.template.InputError(
                        'package requires a {}'.format(parameter))

    def instantiate(self, tmpl):
        super().instantiate(tmpl)

        def pkg_file(*name):
            p = os.path.join(self._packagedir, *name)
            assert os.path.exists(p)
            return p

        # Manually merge Spicy analyzer-specific changes to `zkg.meta`.
        with open(pkg_file('zkg.meta'), 'ab') as f:
            # Add a build command.
            f.write(b'build_command = mkdir -p build && cd build && cmake .. && cmake --build .\n')

        # Manually merge Spicy analyzer-specific changes to `testing/btest.cfg`.
        cfg = pkg_file('testing', 'btest.cfg')
        with open(cfg, 'rb') as f:
            data = f.readlines()
        with open(cfg, 'wb') as f:
            for line in data:
                # Patch in support for `analyzer` testdir.
                if line.startswith(b'TestDirs'):
                    line = bytearray(line.rstrip())
                    line.extend(b' analyzer\n')
                f.write(line)

            f.write(b'DIST=%(testbase)s/..\n')

            f.write(bytes(textwrap.dedent('''
                # Set compilation-related variables to well-defined state.
                CC=
                CXX=
                CFLAGS=
                CPPFLAGS=
                CXXFLAGS=
                LDFLAGS=
                DYLDFLAGS=
                '''), 'ascii'))

        # Manually merge Spicy analyzer-specific changes to `scripts/__load__.zeek`.
        with open(pkg_file('scripts', '__load__.zeek'), 'ab') as f:
            f.write(b'@load-sigs ./dpd.sig\n')


class Template(zeekpkg.template.Template):
    def define_user_vars(self):
        # Try to determine user name and email via the git config. This relies
        # on the fact that zkg itself must have the git module available.
        author = None
        try:
            parser = git.GitConfigParser(config_level='global')
            user_name = parser.get('user', 'name', fallback=None)
            user_email = parser.get('user', 'email', fallback=None)
            if user_name and user_email:
                author = user_name + ' <' + user_email + '>'
        except (NameError, AttributeError):
            pass

        return [
            zeekpkg.uservar.UserVar(
                'name', desc='the name of the package, e.g. "FooBar"'),
            zeekpkg.uservar.UserVar(
                'namespace', desc='a namespace for the package, e.g. "MyOrg"'),
            zeekpkg.uservar.UserVar(
                'author', default=author, desc='your name and email address'),
            zeekpkg.uservar.UserVar(
                'license', desc='one of ' + ', '.join(License().license_keys(self)))
        ]

    def apply_user_vars(self, uvars):
        for uvar in uvars:
            if uvar.name() == 'name':
                self.define_param('name', uvar.val())
                self.define_param('slug', zeekpkg.uservar.slugify(uvar.val()))

            if uvar.name() == 'namespace':
                self.define_param('ns', uvar.val(''))
                self.define_param('ns_colons', uvar.val() + '::' if uvar.val() else '')
                self.define_param('ns_underscore', uvar.val() + '_' if uvar.val() else '')

            if uvar.name() == 'author':
                self.define_param('author', uvar.val())

            if uvar.name() == 'license':
                self.define_param('license', uvar.val())

        self.define_param('year', str(date.today().year))

    def package(self):
        return Package()

    def features(self):
        return [Plugin(), License(), GithubCi(), SpicyAnalyzer()]
