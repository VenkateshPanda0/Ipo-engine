"""
Optional network features of the web app, and the only place in the screening app that may use the
network: sign-in with an identity provider, and later webhooks, e-mail and object storage.

Nothing here is imported unless the feature is switched on, the reader and the analysis never import
it, and the default configuration makes no outbound connection. ``tests/test_offline.py`` enforces
the first two; ``tests/screening/integration/api/test_no_network_by_default.py`` the third.
"""
