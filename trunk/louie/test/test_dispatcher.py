import unittest

import louie
from louie import dispatcher


def x(a):
    return a


class Dummy(object):
    pass


class Callable(object):

    def __call__(self, a):
        return a

    def a(self, a):
        return a


class TestDispatcher(unittest.TestCase):

    def setUp(self):
        louie.reset()

    def tearDown(self):
        """Assert that everything has been cleaned up automatically"""
        assert len(dispatcher.senders_back) == 0, dispatcher.senders_back
        assert len(dispatcher.connections) == 0, dispatcher.connections
        assert len(dispatcher.senders) == 0, dispatcher.senders
    
    def test_Exact(self):
        a = Dummy()
        signal = 'this'
        louie.connect(x, signal, a)
        expected = [(x, a)]
        result = louie.send('this', named=dict(a=a), sender=a)
        assert result == expected, (
            "Send didn't return expected result:\n\texpected:%s\n\tgot:%s"
            % (expected, result))
        louie.disconnect(x, signal, a)
        assert len(list(louie.get_all_receivers(a, signal))) == 0
        
    def test_AnonymousSend(self):
        a = Dummy()
        signal = 'this'
        louie.connect(x, signal)
        expected = [(x, a)]
        result = louie.send(signal, named=dict(a=a))
        assert result == expected, (
            "Send didn't return expected result:\n\texpected:%s\n\tgot:%s"
            % (expected, result))
        louie.disconnect(x, signal)
        assert len(list(louie.get_all_receivers(None, signal))) == 0
        
    def test_AnyRegistration(self):
        a = Dummy()
        signal = 'this'
        louie.connect(x, signal, louie.Any)
        expected = [(x, a)]
        result = louie.send('this', named=dict(a=a), sender=object())
        assert result == expected, (
            "Send didn't return expected result:\n\texpected:%s\n\tgot:%s"
            % (expected, result))
        louie.disconnect(x, signal, louie.Any)
        expected = []
        result = louie.send('this', named=dict(a=a), sender=object())
        assert result == expected, (
            "Send didn't return expected result:\n\texpected:%s\n\tgot:%s"
            % (expected, result))
        assert len(list(louie.get_all_receivers(louie.Any, signal))) == 0
        
    def test_AllRegistration(self):
        a = Dummy()
        signal = 'this'
        louie.connect(x, louie.All, a)
        expected = [(x, a)]
        result = louie.send('this', named=dict(a=a), sender=a)
        assert result == expected, (
            "Send didn't return expected result:\n\texpected:%s\n\tgot:%s"
            % (expected, result))
        louie.disconnect(x, louie.All, a)
        assert len(list(louie.get_all_receivers(a, louie.All))) == 0
        
    def test_GarbageCollected(self):
        a = Callable()
        b = Dummy()
        signal = 'this'
        louie.connect(a.a, signal, b)
        expected = []
        del a
        result = louie.send('this', named=dict(a=b), sender=b)
        assert result == expected, (
            "Send didn't return expected result:\n\texpected:%s\n\tgot:%s"
            % (expected, result))
        assert len(list(louie.get_all_receivers(b, signal))) == 0, (
            "Remaining handlers: %s" % (louie.get_all_receivers(b, signal),))
        
    def test_GarbageCollectedObj(self):
        class x:
            def __call__(self, a):
                return a
        a = Callable()
        b = Dummy()
        signal = 'this'
        louie.connect(a, signal, b)
        expected = []
        del a
        result = louie.send('this', named=dict(a=b), sender=b)
        assert result == expected, (
            "Send didn't return expected result:\n\texpected:%s\n\tgot:%s"
            % (expected, result))
        assert len(list(louie.get_all_receivers(b, signal))) == 0, (
            "Remaining handlers: %s" % (louie.get_all_receivers(b, signal),))

    def test_MultipleRegistration(self):
        a = Callable()
        b = Dummy()
        signal = 'this'
        louie.connect(a, signal, b)
        louie.connect(a, signal, b)
        louie.connect(a, signal, b)
        louie.connect(a, signal, b)
        louie.connect(a, signal, b)
        louie.connect(a, signal, b)
        result = louie.send(signal, named=dict(a=b), sender=b)
        assert len(result) == 1, result
        assert len(list(louie.get_all_receivers(b, signal))) == 1, (
            "Remaining handlers: %s" % (louie.get_all_receivers(b, signal),))
        print id(b)
        print id(signal)
        for key, value in locals().items():
            print key, id(value)
        del result

    def test_robust(self):
        """Test the sendRobust function."""
        def fails():
            raise ValueError('this')
        a = object()
        signal = 'this'
        louie.connect(fails, louie.All, a)
        result = louie.send_robust('this', named=dict(a=a), sender=a)
        err = result[0][1]
        assert isinstance(err, ValueError)
        assert err.args == ('this', )

    def test_extra_connect_args(self):
        r1_args = []
        r1_named = []
        def receiver1(*args, **named):
            r1_args.append(args)
            r1_named.append(named)
        signal = 'foo'
        louie.connect(
            receiver1,
            signal,
            arguments=(1, 2),
            named=dict(a=3, b=4),
            )
        args = (5, 6)
        named = dict(a=7, c=8)
        louie.send(signal, args, named)
        last_args = r1_args[-1]
        last_named = r1_named[-1]
        print last_args, last_named
        assert tuple(last_args) == (1, 2, 5, 6)
        assert last_named['a'] == 7
        assert last_named['b'] == 4
        assert last_named['c'] == 8

