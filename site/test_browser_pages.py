"""User-facing browser game pages must offer a playable link, never raw JSON."""
import unittest,generate
class BrowserPages(unittest.TestCase):
 def test_cards_and_pages(self):
  games=generate.load_web_games();self.assertGreater(len(games),0)
  for game in games:
   with self.subTest(game=game['id']):
    card=generate.web_card(game);page=generate.browser_game_page(game)
    self.assertNotIn('/game.json',card);self.assertIn('browser/'+game['id']+'/',card)
    self.assertIn('<!doctype html>',page);self.assertIn('../../play/'+game['url'],page)
    self.assertIn(game['title'],page);self.assertIn('Controls',page)
    if generate.browser_download(game):
     self.assertIn('Install for Windows',card);self.assertIn('SHA-256:',page)
     self.assertIn('Four hearts',page);self.assertIn('F toggles fullscreen',page)
if __name__=='__main__':unittest.main()
