import unittest

from cloud_mail_client import CloudMailClient


class VerificationCodeExtractionTest(unittest.TestCase):
    def test_extracts_six_digit_code_grouped_by_space(self):
        content = """
        Hello!
        We have sent a verification code to your email address.
        Please enter the code below to verify your account.
        331 781
        This code will expire in 10 minutes.
        If you didn't request this verification, please ignore this email.
        """

        code = CloudMailClient.extract_verification_code(content)

        self.assertEqual(code, "331781")


if __name__ == "__main__":
    unittest.main()
