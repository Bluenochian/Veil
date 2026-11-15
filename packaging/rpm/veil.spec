Name:           veil
Version:        1.0
Release:        1%{?dist}
Summary:        Local Linux browser privacy companion

License:        LicenseRef-PolyForm-Noncommercial-1.0.0
URL:            https://github.com/Bluenochian/Veil
Source0:        Veil-v%{version}-release.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel
BuildRequires:  systemd-rpm-macros
Requires:       python3-pyside6
Requires:       python3-cryptography
Requires:       libsecret
Requires:       libnotify
Requires:       wl-clipboard
Requires:       xclip

%description
Veil conceals matching browser tabs and stages bookmarks in an
encrypted local vault. It provides a desktop tray, command-line controls,
and native-messaging integration for supported browsers.

%prep
%autosetup -n Veil

%build
%py3_build

%install
%py3_install
install -D -p -m 0644 packaging/desktop/veil.desktop %{buildroot}%{_datadir}/applications/veil.desktop
install -D -p -m 0644 assets/icons/veil.png %{buildroot}%{_datadir}/pixmaps/veil.png
install -D -p -m 0644 packaging/systemd/veil.service %{buildroot}%{_userunitdir}/veil.service

%files
%license LICENSE
%doc README.md
%{_bindir}/veil
%{_bindir}/veil-native-host
%{python3_sitelib}/veil*
%{_datadir}/applications/veil.desktop
%{_datadir}/pixmaps/veil.png
%{_userunitdir}/veil.service

%changelog
* Wed Nov 11 2026 Bluenochian <33797102+Bluenochian@users.noreply.github.com> - 1.0-1
- Package browser extensions, desktop integration, and encrypted vault support
