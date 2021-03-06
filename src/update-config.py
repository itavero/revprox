#!/usr/bin/env python3
import argparse
from git import Repo
from pathlib import Path
import sys
from blessings import Terminal
import os
import yaml
import pprint
import sewer
import traceback
from datetime import datetime, timedelta
from OpenSSL import crypto
import nginx
from shutil import which


def create_dir(directory_path):
    p = Path(directory_path)
    if p.exists():
        if not p.is_dir():
            sys.exit('Path exists but is not a directory: ' + directory_path)
        if not os.access(str(p), os.W_OK):
            sys.exit('Path is not readable: ' + directory_path)
        return
    try:
        p.mkdir(parents=True, exist_ok=True)
    except:
        sys.exit('Failed to create storage path.\n' + traceback.format_exc())


def all_subclasses(cls):
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in all_subclasses(c)])


def all_available_dns_types():
    result = {}
    for cls in all_subclasses(sewer.BaseDns):
        key = cls.__name__
        try:
            if cls.dns_provider_name:
                key = cls.dns_provider_name
        except AttributeError:
            print('{t.normal}No DNS provider name in class {t.bold}{name}'.format(t=Terminal(), name=key))
        result[key] = cls
    return result


def should_renew_cert(cert_file):
    if cert_file.exists():
        existing_cert = None
        with open(cert_file, 'r') as stream:
            existing_cert = crypto.load_certificate(crypto.FILETYPE_PEM, stream.read())
        expire_date = datetime.strptime(
            existing_cert.get_notAfter().decode("utf-8"), "%Y%m%d%H%M%SZ")
        threshold = datetime.now() + timedelta(weeks=+2)
        if expire_date < threshold:
            return True
    return False


def get_certs(domain, cert_dir, dns_class, email):
    try:
        create_dir(cert_dir)

        cert_file = cert_dir / 'certificate.crt'
        cert_key_file = cert_dir / 'certificate.key'
        account_key_file = cert_dir / 'account.key'

        renew = False
        account_key = None
        if cert_file.exists() and cert_key_file.exists() and account_key_file.exists():
            renew = should_renew_cert(cert_file)
            if not renew:
                return True
            with open(account_key_file, 'r') as stream:
                account_key = stream.read()

        client = sewer.Client(domain_name=domain, dns_class=dns_class, account_key=account_key)
        certificate = None
        if renew:
            print('{t.normal}Renewing certificate for {t.magenta}{t.bold}{domain}{t.normal}...'.format(
                t=Terminal(), domain=domain))
            certificate = client.renew()
        else:
            print('{t.normal}Requesting new certificate for {t.magenta}{t.bold}{domain}{t.normal}...'.format(
                t=Terminal(), domain=domain))
            certificate = client.cert()
        certificate_key = client.certificate_key

        with open(cert_file, 'w') as f:
            f.write(certificate)
        with open(cert_key_file, 'w') as f:
            f.write(certificate_key)

        if account_key is None:
            account_key = client.account_key
            with open(account_key_file, 'w') as f:
                f.write(account_key)
        return True
    except Exception:
        print('{t.normal}{t.bold}{t.red}Failed to get certificate for domain {domain}, due to error: {e}{t.normal}'.format(
            t=Terminal(), e=traceback.format_exc(), domain=domain))
        return False


def generation_comment(what, subject):
    now = datetime.now().strftime("%H:%M on %B %d, %Y")
    return '{w} for {s}, generated by revprox at {t}'.format(w=what, s=subject, t=now)


def create_nginx_config_for_domain(domain, subdomains, subdomain_dir, forward_others, use_ssl, cert_dir):
    c = nginx.Conf()
    c.add(nginx.Comment(generation_comment('NGINX config', domain)))
    for subdomain in subdomains:
        c.add(nginx.Key('include', str(subdomain_dir / '{}.cfg'.format(subdomain))))

    if forward_others is not None:
        others = nginx.Server()
        others.add(
            nginx.Comment('Forward remaining (sub)domains to ' + forward_others),
            nginx.Key('server_name', '{domain} *.{domain}'.format(domain=domain)),
            nginx.Key('return', '302 {}$request_uri'.format(forward_others)),
            nginx.Key('listen', '80')
        )
        if use_ssl:
            others.add(
                nginx.Comment('use_ssl = True'),
                nginx.Key('listen', '443 ssl'),
                nginx.Key('ssl', 'on'),
                nginx.Key('ssl_certificate', str(cert_dir / 'certificate.crt')),
                nginx.Key('ssl_certificate_key', str(cert_dir / 'certificate.key'))
            )
        c.add(others)

    return c


def create_nginx_config_for_subdomain(domain, subdomain, destination, use_ssl, force_ssl, cert_dir):
    full_domain = '{sub}.{main}'.format(main=domain, sub=subdomain)
    c = nginx.Conf()
    c.add(nginx.Comment(generation_comment('NGINX config', full_domain)))
    if use_ssl and force_ssl:
        non_ssl = nginx.Server()
        non_ssl.add(
            nginx.Comment('force_ssl = True'),
            nginx.Key('listen', '80'),
            nginx.Key('server_name', full_domain),
            nginx.Key('return', '301 https://$host$request_uri')
        )
        c.add(non_ssl)

    main = nginx.Server()
    if not force_ssl:
        main.add(
            nginx.Comment('force_ssl = False'),
            nginx.Key('listen', '80')
        )
    proto = 'http'
    if use_ssl:
        proto = 'https'
        main.add(
            nginx.Comment('use_ssl = True'),
            nginx.Key('listen', '443 ssl'),
            nginx.Key('ssl', 'on'),
            nginx.Key('ssl_certificate', str(cert_dir / 'certificate.crt')),
            nginx.Key('ssl_certificate_key', str(cert_dir / 'certificate.key'))
        )
    main.add(
        nginx.Key('server_name', full_domain),
        nginx.Location('/',
                       nginx.Key('proxy_set_header', 'Host $host'),
                       nginx.Key('proxy_set_header', 'X-Real-IP $remote_addr'),
                       nginx.Key('proxy_set_header', 'X-Forwarded-For $proxy_add_x_forwarded_for'),
                       nginx.Key('proxy_set_header', 'X-Forwarded-Proto $scheme'),
                       nginx.Key('proxy_set_header', 'Upgrade $http_upgrade'),
                       nginx.Key('proxy_set_header', 'Connection $connection_upgrade'),
                       nginx.Key('proxy_pass', destination),
                       nginx.Key('proxy_read_timeout', '90'),
                       nginx.Key('proxy_redirect',
                                 '{dst} {proto}://{full}'.format(dst=destination, full=full_domain, proto=proto))
                       )
    )
    c.add(main)
    return c


parser = argparse.ArgumentParser(
    description='Check if a new config is available from Git and update all files accordingly, if an update is available')
parser.add_argument('-f', '--force', dest='forced', action='store_true',
                    help='Force refresh of generated files.')
parser.add_argument('storage', help='Storage directory')
parser.set_defaults(forced=False)

args = parser.parse_args()

storage = Path(args.storage)
if not storage.exists() or not storage.is_dir() or not os.access(str(storage), os.R_OK) or not os.access(str(storage), os.W_OK):
    sys.exit('Storage directory does not exists or insufficient access.')

repo_path = storage / 'config'
cert_path = storage / 'certs'
nginx_path = storage / 'nginx'

# Check if an update is available
repo = Repo(str(repo_path))
old_hash = repo.head.object.hexsha
repo.remotes.origin.fetch()
repo.git.reset('--hard', repo.active_branch.tracking_branch().name)
new_hash = repo.head.object.hexsha

generate_config = args.forced
if old_hash != new_hash:
    generate_config = True
    print('{t.normal}Detected change on {t.bold}{t.yellow}{branch}{t.normal}. Updated from {t.bold}{t.magenta}{old}{t.normal} to {t.bold}{t.magenta}{new}{t.normal}.'.format(
        t=Terminal(), branch=repo.active_branch.name, old=old_hash, new=new_hash))

renew_certificates = False
if not generate_config:
    # Quick scan for certificates that should be renewed
    for cert in cert_path.glob('**/*.crt'):
        if should_renew_cert(cert):
            renew_certificates = True
            break
    if not renew_certificates:
        # No need to continue
        sys.exit()

# Read config file
config_file = repo_path / 'config.yml'
if not config_file.exists():
    sys.exit('File config.yml not found in repository. Please try again.')
config = None
with open(config_file, 'r') as stream:
    try:
        config = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        sys.exit('{t.normal}{t.bold}{t.red}Failed to load config, due to error: {e}{t.normal}'.format(
            t=Terminal(), e=exc))

if config is None:
    sys.exit('{t.normal}{t.bold}{t.red}Failed to load config.{t.normal}'.format(t=Terminal()))
# Uncomment the following line for development/debugging purposes
# pprint.pprint(repr(config))

# Process DNS providers
dns_types = all_available_dns_types()
dns_providers = {}
for (provider, cfg) in config['dns'].items():
    try:
        dns_type = cfg['type']
        if dns_type not in dns_types:
            sys.exit('{t.normal}{t.bold}{t.red}Unknown DNS provider type: {type}. Available types: "{avail}".{t.normal}'.format(
                t=Terminal(), type=dns_type, avail='", "'.join(dns_types.keys())))
        dns_providers[provider] = dns_types[dns_type](**cfg['config'])
    except:
        print('{t.normal}Init DNS provider failed for {t.bold}{t.magenta}{provider}{t.normal}.\n{t.red}{error}{t.normal}'.format(
            t=Terminal(), provider=provider, error=traceback.format_exc()))

default_dns = 'default'
if default_dns not in dns_providers:
    if len(dns_providers.keys()) > 0:
        default_dns = dns_providers.keys()[0]
    else:
        sys.exit(
            '{t.normal}{t.bold}{t.red}No valid DNS provider configuration!{t.normal}'.format(t=Terminal()))
print('{t.normal}Using DNS provider {t.bold}{t.magenta}{provider}{t.normal} as the default provider.'.format(
    t=Terminal(), provider=default_dns))


# Process domain configuration
domain_names = []
for (domain, cfg) in config['domains'].items():
    try:
        # Prepare directories
        domain_cert = cert_path / domain
        create_dir(domain_cert)
        domain_nginx = nginx_path / domain
        create_dir(domain_nginx)
        subdomain_nginx = domain_nginx / 'subdomains'
        create_dir(subdomain_nginx)

        # Create / refresh certificates
        use_ssl = False
        force_ssl = False
        if 'ssl' in cfg and 'enabled' in cfg['ssl'] and cfg['ssl']['enabled']:
            use_ssl = True
            force_ssl = ('forced' in cfg['ssl'] and cfg['ssl']['forced'])
            if 'email' not in cfg['ssl']:
                print('{t.normal}{t.red}{t.bold}If you wish to use SSL for domain {domain}, you MUST configure an "email".{t.normal}'.format(
                    t=Terminal(), domain=domain))
                continue
            ssl_email = cfg['ssl']['email']
            cert_domain = '*.{domain}'.format(domain=domain)
            dns_class = dns_providers[default_dns]
            if 'dns' in cfg:
                dns_key = cfg['dns']
                if dns_key in dns_providers:
                    dns_class = dns_provider[dns_key]
                else:
                    print('{t.normal}{t.red}{t.bold}Domain "{domain}" is configured to use DNS provider "{dns}", but it is not found or not properly configured.{t.normal}'.format(
                        t=Terminal(), domain=domain, dns=dns_key))
                    continue
            if not get_certs(cert_domain, domain_cert, dns_class, ssl_email):
                print('{t.normal}{t.red}{t.bold}Failed to get certificates for "{domain}".{t.normal}'.format(
                    t=Terminal(), domain=domain))
                continue

        if generate_config:
            # NGINX config
            subdomains = []
            for (subdomain, destination) in cfg['subdomains'].items():
                sub_cfg = create_nginx_config_for_subdomain(
                    domain, subdomain, destination, use_ssl, force_ssl, domain_cert)
                nginx.dumpf(sub_cfg, str(subdomain_nginx / '{}.cfg'.format(subdomain)))
                subdomains.append(subdomain)

            # Forward others?
            forward_others = None
            if 'forward_others' in cfg and cfg['forward_others']:
                forward_others = cfg['forward_others']

            main_cfg = create_nginx_config_for_domain(
                domain, subdomains, subdomain_nginx, forward_others, use_ssl, domain_cert)
            nginx.dumpf(main_cfg, str(domain_nginx / 'main.cfg'))
            domain_names.append(domain)
    except:
        print('{t.normal}Processing failed for domain {t.bold}{t.magenta}{domain}{t.normal}.\n{t.red}{error}{t.normal}'.format(
            t=Terminal(), domain=domain, error=traceback.format_exc()))

# Generate main revprox NGINX config file
if generate_config:
    rp_config = nginx.Conf()
    map = nginx.Map('$http_upgrade $connection_upgrade')
    map.add(
        nginx.Key('default', 'upgrade'),
        nginx.Key('\'\'', 'close')
    )
    rp_config.add(
        nginx.Comment(generation_comment('Main configuration', 'NGINX')),
        nginx.Comment('This file needs to be included in your NGINX configuration.'),
        map
    )
    for domain in domain_names:
        rp_config.add(nginx.Key('include', str(nginx_path / domain / 'main.cfg')))
    nginx.dumpf(rp_config, str(nginx_path / 'revprox.cfg'))


# Clean up old, unused configuration files
# TODO clean up

# Validate new configuration
nginx_exec = which('nginx')
if nginx_exec is not None:
    if os.system('{exec} -t'.format(exec=nginx_exec)) > 0:
        sys.exit('{t.normal}NGINX config {t.red}{t.bold}INVALID{t.normal} - {t.bold}Please fix this manually!{t.normal}'.format(t=Terminal()))

# Check if NGINX will use configuration
# TODO create check

# Restart NGINX with new configuration
if generate_config or renew_certificates:
    is_restarted = False
    # - FreeBSD (and possibly others)
    service_manager = which('service')
    if service_manager is not None:
        exit_code = os.system('{program} nginx restart'.format(program=service_manager))
        is_restarted = exit_code == 0

    if is_restarted:
        print('{t.normal}Restart NGINX: {t.green}{t.bold}SUCCESS{t.normal}'.format(t=Terminal()))
    else:
        print('{t.normal}Restart NGINX: {t.red}{t.bold}FAILED{t.normal} - {t.bold}Please restart NGINX manually!{t.normal}'.format(t=Terminal()))
