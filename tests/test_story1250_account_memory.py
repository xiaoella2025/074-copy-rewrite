"""Verify existing 074 account persistence; no real service or user data."""
import tempfile
import unittest
from unittest.mock import patch
import management


class VerifiedBindingMemoryTests(unittest.TestCase):
    def test_confirmed_binding_survives_backend_restart_and_is_sent_to_same_service(self):
        with tempfile.TemporaryDirectory() as root:
            service=management.Service(root)
            service.configure({'url':'https://fixture.invalid','enabled':{'account':True}})
            with patch.object(service,'_request',return_value={'ok':True,'data':{}}):
                service.call('account','bind',{'email':'owner@example.invalid','verificationToken':'fixture-verified'})
            restarted=management.Service(root)
            self.assertEqual(restarted.status()['email'],'owner@example.invalid')
            with patch.object(restarted,'_request',return_value={'ok':True,'data':{'bound':True,'email':'owner@example.invalid'}}) as request:
                restarted.call('account','balance',{})
            self.assertEqual(request.call_args.args[1]['boundEmail'],'owner@example.invalid')

    def test_failed_binding_is_not_remembered_and_switching_service_clears_old_identity(self):
        with tempfile.TemporaryDirectory() as root:
            service=management.Service(root)
            service.configure({'url':'https://fixture.invalid','enabled':{'account':True}})
            with patch.object(service,'_request',return_value={'ok':False,'error':{'message':'fixture rejected'}}):
                with self.assertRaises(management.ServiceError):
                    service.call('account','bind',{'email':'owner@example.invalid','verificationToken':'fixture-rejected'})
            self.assertEqual(management.Service(root).status()['email'],'')
            with patch.object(service,'_request',return_value={'ok':True,'data':{}}):
                service.call('account','bind',{'email':'owner@example.invalid','verificationToken':'fixture-verified'})
            service.configure({'url':'https://another-fixture.invalid'})
            self.assertEqual(management.Service(root).status()['email'],'')


if __name__=='__main__':unittest.main()
