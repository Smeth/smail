"""Prépare hors réseau quatre flèches Lucide pour la feuille de style Qt."""
from pathlib import Path

if __name__ == '__main__':
    root = Path(__file__).parent / 'assets'
    source = (root / 'icons' / 'chevron-down.svg').read_text(encoding='utf-8')
    destination = root / 'style-icons'
    destination.mkdir(exist_ok=True)
    for theme,color in [('clair','#56657A'),('sombre','#B0BDD0')]:
        down = source.replace('currentColor',color)
        start,end = down.index('>')+1,down.rindex('</svg>')
        up = down[:start]+'<g transform="rotate(180 12 12)">'+down[start:end]+'</g>'+down[end:]
        (destination / f'down-{theme}.svg').write_text(down,encoding='utf-8')
        (destination / f'up-{theme}.svg').write_text(up,encoding='utf-8')
    print('Quatre flèches de style locales préparées ; licence Lucide conservée.')
