import unittest
from backend.main import validate
class ValidationTests(unittest.TestCase):
    def test_valid(self): validate(0,30,.85,'base')
    def test_invalid(self):
        for args in [(0,0,1,'base'),(-1,30,1,'base'),(0,601,1,'base'),(0,30,.2,'base'),(0,30,1,'bad'),(float('nan'),30,1,'base')]:
            with self.subTest(args=args), self.assertRaises(ValueError): validate(*args)
