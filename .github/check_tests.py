"""Verdict des tests d'après le rapport JUnit, et non d'après le code de sortie de pytest.

Avec PySide6 6.12, le processus Python plante en violation d'accès à sa fermeture (destruction de
Qt WebEngine), après la fin de tous les tests et l'écriture du rapport : le code de sortie (139)
ne reflète alors pas le résultat. Le rapport JUnit n'est écrit qu'en fin de session complète, donc
un plantage pendant les tests reste un échec.

Usage : python .github/check_tests.py test-results.xml <code de sortie de pytest>
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

report, code = Path(sys.argv[1]), int(sys.argv[2])
if not report.exists():
    print(f'::error title=Tests::Aucun rapport JUnit : pytest s’est arrêté avant la fin (code {code}).')
    sys.exit(1)
root = ET.parse(report).getroot()
suites = [root] if root.tag == 'testsuite' else list(root.iter('testsuite'))
count = {key: sum(int(suite.get(key, 0)) for suite in suites) for key in ('tests', 'failures', 'errors')}
print(f"{count['tests']} test(s), {count['failures']} échec(s), {count['errors']} erreur(s) ; code de sortie de pytest : {code}")
if count['tests'] == 0 or count['failures'] or count['errors']:
    sys.exit(1)
if code not in (0, 1, 2, 3, 4, 5):
    print(f'::warning title=Fermeture de Python::Tous les tests ont réussi, puis le processus a planté à sa fermeture (code {code}) : '
          'plantage connu de Qt WebEngine (PySide6 6.12) lors de la destruction des objets, sans effet sur les résultats.')
elif code != 0:
    sys.exit(1)  # pytest signale un problème que le rapport ne montre pas (collecte, interruption…).
