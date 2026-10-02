import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server


class ImaStatusTests(unittest.TestCase):
    def test_local_credentials_are_not_reported_as_verified_connection(self):
        with patch.object(server, "load_settings", return_value={
            "ima": {"client_id": "fake-client", "api_key": "fake-key"}
        }):
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                conn.request("POST", "/api/test_ima", b"{}", {"Content-Type": "application/json"})
                response = conn.getresponse()
                data = json.loads(response.read())
                conn.close()
                self.assertEqual(response.status, 200)
                self.assertTrue(data["ok"])
                self.assertFalse(data["verified"])
                self.assertNotIn("fake-key", json.dumps(data))
            finally:
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
