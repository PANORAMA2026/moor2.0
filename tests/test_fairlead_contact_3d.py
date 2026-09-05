import unittest
from core.fairlead_contact_3d import solve_cylindrical_contact_3d

class FairleadContact3DTests(unittest.TestCase):
    def test_straight_line_through_roller_has_half_turn_contact(self):
        result=solve_cylindrical_contact_3d((-10.,0.,0.),(10.,0.,0.),(0.,0.,0.),(0.,0.,1.),1000.)
        self.assertEqual(result["status"],"GEOMETRY_ONLY")
        self.assertAlmostEqual(result["contact_angle_deg"],180.,places=8)

    def test_bent_route_has_valid_contact_angle(self):
        result=solve_cylindrical_contact_3d((-10.,0.,0.),(0.,10.,0.),(0.,0.,0.),(0.,0.,1.),1000.)
        self.assertEqual(result["status"],"GEOMETRY_ONLY")
        self.assertGreater(result["contact_angle_deg"],0.)
        self.assertLessEqual(result["contact_angle_deg"],180.)

    def test_point_inside_roller_is_rejected(self):
        result=solve_cylindrical_contact_3d((0.1,0.,0.),(10.,0.,0.),(0.,0.,0.),(0.,0.,1.),1000.)
        self.assertEqual(result["status"],"POINT_NOT_EXTERNAL_TO_ROLLER")

if __name__=="__main__":
    unittest.main()
