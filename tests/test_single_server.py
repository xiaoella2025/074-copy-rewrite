"""Only one app074 server may own its listening port."""

import unittest

import server


class SingleServerTests(unittest.TestCase):
    def test_second_server_cannot_bind_same_local_port(self):
        first = server.SingleInstanceHTTPServer(("127.0.0.1", 0), server.Handler)
        try:
            with self.assertRaises(OSError):
                second = server.SingleInstanceHTTPServer(
                    ("127.0.0.1", first.server_port), server.Handler
                )
                second.server_close()
        finally:
            first.server_close()


if __name__ == "__main__":
    unittest.main()
