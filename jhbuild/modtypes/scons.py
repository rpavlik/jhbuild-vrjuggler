# jhbuild - a build script for GNOME 1.x and 2.x
# Copyright (C) 2001-2006  James Henstridge
# Copyright (C) 2007-2008  Frederic Peters
#
#   autotools.py: autotools module type definitions.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

__metaclass__ = type

import os
import re
import stat

from jhbuild.errors import FatalError, BuildStateError, CommandError
from jhbuild.modtypes import \
     Package, DownloadableModule, get_dependencies, get_branch, register_module_type

__all__ = [ 'AutogenModule' ]

class SconsModule(Package, DownloadableModule):
    '''Base type for modules that build using Scons.  Subclasses are
    responsible for downloading/updating the working copy.'''
    type = 'scons'

    PHASE_CHECKOUT = DownloadableModule.PHASE_CHECKOUT
    PHASE_FORCE_CHECKOUT = DownloadableModule.PHASE_FORCE_CHECKOUT
    PHASE_CLEAN          = 'clean'
    PHASE_DISTCLEAN      = 'distclean'
    PHASE_CONFIGURE      = 'configure'
    PHASE_BUILD          = 'build'
    PHASE_CHECK          = 'check'
    PHASE_DIST           = 'dist'
    PHASE_INSTALL        = 'install'

    def __init__(self, name, branch, sconsargs='prefix=%(prefix)',
                 dependencies=[], after=[], suggests=[],
                 supports_non_srcdir_builds=False):
        Package.__init__(self, name, dependencies, after, suggests)
        self.branch = branch
        self.sconsargs = sconsargs
        self.supports_non_srcdir_builds = supports_non_srcdir_builds

    def get_srcdir(self, buildscript):
        return self.branch.srcdir

    def get_builddir(self, buildscript):
        if buildscript.config.buildroot and self.supports_non_srcdir_builds:
            d = buildscript.config.builddir_pattern % (
                os.path.basename(self.get_srcdir(buildscript)))
            return os.path.join(buildscript.config.buildroot, d)
        else:
            return self.get_srcdir(buildscript)

    def get_revision(self):
        return self.branch.tree_id()

    def skip_configure(self, buildscript, last_phase):
    	return False # never

    def do_configure(self, buildscript):
        builddir = self.get_builddir(buildscript)
        if buildscript.config.buildroot and not os.path.exists(builddir):
            os.makedirs(builddir)
        buildscript.set_action(_('Configuring'), self)
    do_configure.depends = [PHASE_CHECKOUT]
    do_configure.error_phases = [PHASE_FORCE_CHECKOUT,
            PHASE_CLEAN, PHASE_DISTCLEAN]

    def skip_clean(self, buildscript, last_phase):
        builddir = self.get_builddir(buildscript)
        if not os.path.exists(builddir):
            return True
        if not os.path.exists(os.path.join(builddir, self.makefile)):
            return True
        return False

    def do_clean(self, buildscript):
        buildscript.set_action(_('Cleaning'), self)
        makeargs = self.makeargs + ' ' + self.config.module_makeargs.get(
                self.name, self.config.makeargs)
        cmd = '%s %s clean' % (os.environ.get('MAKE', 'make'), makeargs)
        buildscript.execute(cmd, cwd = self.get_builddir(buildscript),
                extra_env = self.extra_env)
    do_clean.depends = [PHASE_CONFIGURE]
    do_clean.error_phases = [PHASE_FORCE_CHECKOUT, PHASE_CONFIGURE]

    def do_build(self, buildscript):
        buildscript.set_action(_('Building'), self)
        sconsargs = self.sconsargs + ' ' + self.config.module_sconsargs.get(
                self.name, self.config.sconsargs)
        vars = {'prefix': buildscript.config.prefix}
        cmd = '%s %s' % (os.environ.get('SCONS', 'scons'), sconsargs % vars)
        buildscript.execute(cmd, cwd = self.get_builddir(buildscript),
                extra_env = self.extra_env)
    do_build.depends = [PHASE_CONFIGURE]
    do_build.error_phases = [PHASE_FORCE_CHECKOUT, PHASE_CONFIGURE,
            PHASE_CLEAN, PHASE_DISTCLEAN]

    def skip_check(self, buildscript, last_phase):
        if not self.check_target:
            return True
        if self.name in buildscript.config.module_makecheck:
            return not buildscript.config.module_makecheck[self.name]
        if 'check' not in buildscript.config.build_targets:
            return True
        return False

    def do_check(self, buildscript):
        pass
    
    def do_dist(self, buildscript):
        pass

    def do_distcheck(self, buildscript):
		pass

    def do_install(self, buildscript):
        buildscript.set_action(_('Installing'), self)
        buildscript.packagedb.add(self.name, self.get_revision() or '')
    do_install.depends = [PHASE_BUILD]

    def do_distclean(self, buildscript):
        buildscript.set_action(_('Distcleaning'), self)

    def skip_uninstall(self, buildscript, last_phase):
        srcdir = self.get_srcdir(buildscript)
        if not os.path.exists(srcdir):
            return True
        if not os.path.exists(os.path.join(srcdir, self.makefile)):
            return True
        return False

    def do_uninstall(self, buildscript):
        buildscript.set_action(_('Uninstalling'), self)
        makeargs = self.makeargs + ' ' + self.config.module_makeargs.get(
                self.name, self.config.makeargs)
        cmd = '%s %s uninstall' % (os.environ.get('MAKE', 'make'), makeargs)
        buildscript.execute(cmd, cwd = self.get_builddir(buildscript),
                extra_env = self.extra_env)
        buildscript.packagedb.remove(self.name)

    def xml_tag_and_attrs(self):
        return ('scons',
                [('sconsargs', 'sconsargs', 'prefix=%(prefix)'),
                 ('id', 'name', None),
                 ('supports-non-srcdir-builds',
                  'supports_non_srcdir_builds', False)])


def parse_scons(node, config, uri, repositories, default_repo):
    id = node.getAttribute('id')
    sconsargs = ''
    supports_non_srcdir_builds = True
    if node.hasAttribute('sconsargs'):
        autogenargs = node.getAttribute('sconsargs')
    if node.hasAttribute('supports-non-srcdir-builds'):
        supports_non_srcdir_builds = \
            (node.getAttribute('supports-non-srcdir-builds') != 'no')

    # Make some substitutions; do special handling of '${prefix}' and '${libdir}'
    p = re.compile('(\${prefix})')
    sconsargs     = p.sub(config.prefix, sconsargs)
    # I'm not sure the replacement of ${libdir} is necessary for firefox...
    p = re.compile('(\${libdir})')
    libsubdir = '/lib'
    if config.use_lib64:
        libsubdir = '/lib64'
    sconsargs     = p.sub(config.prefix + libsubdir, autogenargs)

    dependencies, after, suggests = get_dependencies(node)
    branch = get_branch(node, repositories, default_repo, config)

    return SconsModule(id, branch, sconsargs=sconsargs,
                         dependencies=dependencies,
                         after=after,
                         suggests=suggests,
                         supports_non_srcdir_builds=supports_non_srcdir_builds)
register_module_type('scons', parse_scons)

