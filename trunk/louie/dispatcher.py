"""Multiple-producer-multiple-consumer signal-dispatching.

``dispatcher`` is the core of Louie, providing the primary API and the
core logic for the system.

Internal attributes:

- ``WEAKREF_TYPES``: Tuple of types/classes which represent weak
  references to receivers, and thus must be dereferenced on retrieval
  to retrieve the callable object
        
- ``connections``::

    { sender_id (id) : { signal : [receivers...] } }
    
- ``senders``: Used for cleaning up sender references on sender
  deletion::

    { sender_id (id) : weakref(sender) }
    
- ``senders_back``: Used for cleaning up receiver references on receiver
  deletion::

    { receiver_id (id) : [sender_id (id)...] }
"""

from itertools import izip
import os
import weakref

from louie import error
from louie import robustapply
from louie import saferef
from louie.sender import Any, Anonymous
from louie.signal import All


# Support for statistics.
if __debug__:
    connects = 0
    disconnects = 0
    sends = 0

    def print_stats():
        print ('\n'
               'Louie connects: %i\n'
               'Louie disconnects: %i\n'
               'Louie sends: %i\n'
               '\n') % (connects, disconnects, sends)

    if 'PYDISPATCH_STATS' in os.environ:
        import atexit
        atexit.register(print_stats)



WEAKREF_TYPES = (weakref.ReferenceType, saferef.BoundMethodWeakref)


connections = {}
senders = {}
senders_back = {}
plugins = []

def reset():
    """Reset the state of Louie.

    Useful during unit testing.  Should be avoided otherwise.
    """
    global connections, senders, senders_back, plugins
    connections = {}
    senders = {}
    senders_back = {}
    plugins = []


def connect(receiver, signal=All, sender=Any, weak=True,
            arguments=None, named=None):
    """Connect ``receiver`` to ``sender`` for ``signal``.

    - ``receiver``: A callable Python object which is to receive
      messages/signals/events.  Receivers must be hashable objects.

      If weak is ``True``, then receiver must be weak-referencable (more
      precisely ``saferef.safe_ref()`` must be able to create a
      reference to the receiver).
    
      Receivers are fairly flexible in their specification, as the
      machinery in the ``robustapply`` module takes care of most of the
      details regarding figuring out appropriate subsets of the sent
      arguments to apply to a given receiver.

      Note: If ``receiver`` is itself a weak reference (a callable), it
      will be de-referenced by the system's machinery, so *generally*
      weak references are not suitable as receivers, though some use
      might be found for the facility whereby a higher-level library
      passes in pre-weakrefed receiver references.

    - ``signal``: The signal to which the receiver should respond.
    
      If ``All``, receiver will receive all signals from the indicated
      sender (which might also be ``All``, but is not necessarily
      ``All``).
        
      Otherwise must be a hashable Python object other than ``None``
      (``DispatcherError`` raised on ``None``).
        
    - ``sender``: The sender to which the receiver should respond.
    
      If ``Any``, receiver will receive the indicated signals from any
      sender.
        
      If ``Anonymous``, receiver will only receive indicated signals
      from ``send``/``send_exact`` which do not specify a sender, or
      specify ``Anonymous`` explicitly as the sender.

      Otherwise can be any python object.
        
    - ``weak``: Whether to use weak references to the receiver.
      
      By default, the module will attempt to use weak references to
      the receiver objects.  If this parameter is ``False``, then strong
      references will be used.

    - ``arguments``: Optional sequence of positional arguments to pass
      to the receiver in addition to positional arguments given to a
      ``send`` call. The arguments specified here will precede
      arguments passed given in the ``send`` call.

    - ``named``: Optional dict of named arguments to pass to the
      receiver in addition to named arguments given to a ``send``
      call.  Arguments given in a ``send`` call will override these
      arguments.

    Returns ``None``, may raise ``DispatcherTypeError``.
    """
    if not arguments:
        arguments = ()
    if not named:
        named = {}
    if signal is None:
        raise error.DispatcherTypeError(
            'Signal cannot be None (receiver=%r sender=%r)'
            % (receiver, sender))
    if weak:
        receiver = saferef.safe_ref(receiver, on_delete=_remove_receiver)
    receiver_id = id(receiver)
    print 'receiver', receiver, 'is id', receiver_id
    sender_id = id(sender)
    print 'sender', sender, 'id is', sender_id
    if connections.has_key(sender_id):
        signals = connections[sender_id]
    else:
        connections[sender_id] = signals = {}
    # Keep track of senders for cleanup.
    # Is Anonymous something we want to clean up?
    if sender not in (None, Anonymous, Any):
        def remove(object, sender_id=sender_id):
            _remove_sender(sender_id=sender_id)
        # Skip objects that can not be weakly referenced, which means
        # they won't be automatically cleaned up, but that's too bad.
        try:
            weak_sender = weakref.ref(sender, remove)
            senders[sender_id] = weak_sender
        except:
            pass
    # get current set, remove any current references to
    # this receiver in the set, including back-references
    if signals.has_key(signal):
        receivers, receiver_args = signals[signal]
        print 'removing old back refs', id(receiver), receiver
        _remove_old_back_refs(
            sender_id, signal, receiver, receivers, receiver_args)
    else:
        receivers, receiver_args = signals[signal] = ([], [])
    try:
        current = senders_back.setdefault(receiver_id, [])
        if sender_id not in current:
            current.append(sender_id)
    except:
        pass
    receivers.append(receiver)
    receiver_args.append((arguments, named))
    # Update stats.
    if __debug__:
        global connects
        connects += 1


def disconnect(receiver, signal=All, sender=Any, weak=True):
    """Disconnect ``receiver`` from ``sender`` for ``signal``.

    - ``receiver``: The registered receiver to disconnect.
    
    - ``signal``: The registered signal to disconnect.
    
    - ``sender``: The registered sender to disconnect.
    
    - ``weak``: The weakref state to disconnect.

    ``disconnect`` reverses the process of ``connect``, the semantics for
    the individual elements are logically equivalent to a tuple of
    ``(receiver, signal, sender, weak)`` used as a key to be deleted
    from the internal routing tables.  (The actual process is slightly
    more complex but the semantics are basically the same).

    Note: Using ``disconnect`` is not required to cleanup routing when
    an object is deleted; the framework will remove routes for deleted
    objects automatically.  It's only necessary to disconnect if you
    want to stop routing to a live object.
        
    Returns ``None``, may raise ``DispatcherTypeError`` or
    ``DispatcherKeyError``.
    """
    if signal is None:
        raise error.DispatcherTypeError(
            'Signal cannot be None (receiver=%r sender=%r)'
            % (receiver, sender))
    if weak:
        receiver = saferef.safe_ref(receiver)
    receiver_id = id(receiver)
    sender_id = id(sender)
    try:
        signals = connections[sender_id]
        receivers, receiver_args = signals[signal]
    except KeyError:
        raise error.DispatcherKeyError(
            'No receivers found for signal %r from sender %r' 
            % (signal, sender)
            )
    try:
        # also removes from receivers
        print 'removing old back refs', id(receiver), receiver
        _remove_old_back_refs(
            sender_id, signal, receiver, receivers, receiver_args)
    except ValueError:
        raise error.DispatcherKeyError(
            'No connection to receiver %s for signal %s from sender %s'
            % (receiver, signal, sender)
            )
    _cleanup_connections(sender_id, signal)
    # Update stats.
    if __debug__:
        global disconnects
        disconnects += 1


def get_receivers(sender=Any, signal=All):
    """Get list of receivers from global tables.

    This function allows you to retrieve the raw list of receivers
    from the connections table for the given sender and signal pair.

    Note: There is no guarantee that this is the actual list stored in
    the connections table, so the value should be treated as a simple
    iterable/truth value rather than, for instance a list to which you
    might append new records.

    Normally you would use ``live_receivers(get_receivers(...))`` to
    retrieve the actual receiver objects as an iterable object.
    """
    try:
        receivers, receiver_args = connections[id(sender)][signal]
        return izip(receivers, receiver_args)
    except KeyError:
        return []


def live_receivers(receivers_and_args):
    """Filter sequence of receivers to get resolved, live receivers.

    This is a generator which will iterate over the passed sequence,
    checking for weak references and resolving them, then returning
    all live receivers.
    """
    for receiver, args in receivers_and_args:
        if isinstance(receiver, WEAKREF_TYPES):
            # Dereference the weak reference.
            receiver = receiver()
        if receiver is not None:
            # Check installed plugins to make sure this receiver is
            # live.
            live = True
            for plugin in plugins:
                if not plugin.is_live(receiver):
                    live = False
                    break
            if live:
                yield (receiver, args)
            

def get_all_receivers(sender=Any, signal=All):
    """Get list of all receivers from global tables.

    This gets all receivers which should receive the given signal from
    sender, each receiver should be produced only once by the
    resulting generator.
    """
    receivers = set()
    all_receivers = []
    all_receivers.extend(get_receivers(sender, signal))
    all_receivers.extend(get_receivers(sender, All))
    all_receivers.extend(get_receivers(Any, signal))
    all_receivers.extend(get_receivers(Any, All))
    for receiver, args in all_receivers:
        if receiver:
            if not receiver in receivers:
                receivers.add(receiver)
                yield (receiver, args)


def send(signal=All, arguments=None, named=None, sender=Anonymous):
    """Send ``signal`` from ``sender`` to all connected receivers.
    
    - ``signal``: (Hashable) signal value; see ``connect`` for details.

    - ``arguments``: Positional arguments which will be passed to *all*
      receivers. Note that this may raise ``TypeError`` if the receivers
      do not allow the particular arguments.  Note also that arguments
      are applied before named arguments, so they should be used with
      care.

    - ``named``: Named arguments which will be filtered according to the
      parameters of the receivers to only provide those acceptable to
      the receiver.

    - ``sender``: The sender of the signal.
    
      If ``Any``, only receivers registered for ``Any`` will receive the
      message.

      If ``Anonymous``, only receivers registered to receive messages
      from ``Anonymous`` or ``Any`` will receive the message.

      Otherwise can be any Python object (normally one registered with
      a connect if you actually want something to occur).

    Return a list of tuple pairs ``[(receiver, response), ...]``

    If any receiver raises an error, the error propagates back through
    send, terminating the dispatch loop, so it is quite possible to
    not have all receivers called if a raises an error.
    """
    if not arguments:
        arguments = ()
    if not named:
        named = {}
    # Call each receiver with whatever arguments it can accept.
    # Return a list of tuple pairs [(receiver, response), ... ].
    responses = []
    for receiver, args in live_receivers(
        tuple(get_all_receivers(sender, signal))):
        # Wrap receiver using installed plugins.
        original = receiver
        for plugin in plugins:
            receiver = plugin.wrap_receiver(receiver)
        # Apply additional arguments given for this connection.
        r_args, r_named = args
        r_args = tuple(r_args) + tuple(arguments)
        r_named = r_named.copy()
        r_named.update(named)
        response = robustapply.robust_apply(
            receiver, original,
            signal=signal,
            sender=sender,
            *r_args,
            **r_named
            )
        responses.append((receiver, response))
    # Update stats.
    if __debug__:
        global sends
        sends += 1
    return responses


def send_exact(signal=All, arguments=None, named=None, sender=Anonymous):
    """Send ``signal`` only to receivers registered for exact message.

    ``send_exact`` allows for avoiding ``Any``/``Anonymous`` registered
    handlers, sending only to those receivers explicitly registered
    for a particular signal on a particular sender.
    """
    if not arguments:
        arguments = ()
    if not named:
        named = {}
    responses = []
    for receiver, args in live_receivers(
        tuple(get_receivers(sender, signal))
        ):
        # Wrap receiver using installed plugins.
        original = receiver
        for plugin in plugins:
            receiver = plugin.wrap_receiver(receiver)
        # Apply additional arguments given for this connection.
        r_args, r_named = args
        r_args = tuple(r_args) + tuple(arguments)
        r_named = r_named.copy()
        r_named.update(named)
        response = robustapply.robust_apply(
            receiver, original,
            signal=signal,
            sender=sender,
            *r_args,
            **r_named
            )
        responses.append((receiver, response))
    return responses
    

def send_robust(signal=All, arguments=None, named=None, sender=Anonymous):
    """Send ``signal`` from ``sender`` to all connected receivers catching
    errors

    - ``signal``: (Hashable) signal value, see connect for details

    - ``arguments``: Positional arguments which will be passed to *all*
      receivers. Note that this may raise ``TypeError`` if the receivers
      do not allow the particular arguments.  Note also that arguments
      are applied before named arguments, so they should be used with
      care.

    - ``named``: Named arguments which will be filtered according to the
      parameters of the receivers to only provide those acceptable to
      the receiver.

    - ``sender``: The sender of the signal.
    
      If ``Any``, only receivers registered for ``Any`` will receive the
      message.

      If ``Anonymous``, only receivers registered to receive messages
      from ``Anonymous`` or ``Any`` will receive the message.

      Otherwise can be any Python object (normally one registered with
      a connect if you actually want something to occur).

    Return a list of tuple pairs ``[(receiver, response), ... ]``

    If any receiver raises an error (specifically, any subclass of
    ``Exception``), the error instance is returned as the result for
    that receiver.
    """
    if not arguments:
        arguments = ()
    if not named:
        named = {}
    # Call each receiver with whatever arguments it can accept.
    # Return a list of tuple pairs [(receiver, response), ... ].
    responses = []
    for receiver, args in live_receivers(
        tuple(get_all_receivers(sender, signal))
        ):
        # Wrap receiver using installed plugins.
        original = receiver
        for plugin in plugins:
            receiver = plugin.wrap_receiver(receiver)
        # Apply additional arguments given for this connection.
        r_args, r_named = args
        r_args = tuple(r_args) + tuple(arguments)
        r_named = r_named.copy()
        r_named.update(named)
        try:
            response = robustapply.robust_apply(
                receiver, original,
                signal=signal,
                sender=sender,
                *r_args,
                **r_named
                )
        except Exception, err:
            responses.append((receiver, err))
        else:
            responses.append((receiver, response))
    return responses


def _remove_receiver(receiver):
    """Remove ``receiver`` from connections."""
    if not senders_back:
        # During module cleanup the mapping will be replaced with None.
        return False
    receiver_id = id(receiver)
    print 'removing receiver', receiver, 'id', receiver_id
    for sender_id in senders_back.get(receiver_id, ()):
        try:
            signals = connections[sender_id].keys()
        except KeyError:
            pass
        else:
            for signal in signals:
                try:
                    receivers, receiver_args = connections[sender_id][signal]
                except KeyError:
                    pass
                else:
                    try:
                        index = receivers.index(receiver)
                        del receivers[index]
                        del receiver_args[index]
                    except Exception:
                        pass
                _cleanup_connections(sender_id, signal)
    try:
        del senders_back[receiver_id]
    except KeyError:
        pass

            
def _cleanup_connections(sender_id, signal):
    """Delete empty signals for ``sender_id``. Delete ``sender_id`` if
    empty."""
    try:
        receivers, receiver_args = connections[sender_id][signal]
    except:
        pass
    else:
        if not receivers and not receiver_args:
            # No more connected receivers. Therefore, remove the signal.
            try:
                signals = connections[sender_id]
            except KeyError:
                pass
            else:
                del signals[signal]
                if not signals:
                    # No more signal connections. Therefore, remove the sender.
                    _remove_sender(sender_id)


def _remove_sender(sender_id):
    """Remove ``sender_id`` from connections."""
    _remove_back_refs(sender_id)
    try:
        del connections[sender_id]
    except KeyError:
        pass
    # Sender_id will only be in senders dictionary if sender 
    # could be weakly referenced.
    try:
        del senders[sender_id]
    except:
        pass


def _remove_back_refs(sender_id):
    """Remove all back-references to this ``sender_id``."""
    try:
        signals = connections[sender_id]
    except KeyError:
        signals = None
    else:
        items = signals.items()
        def all_receiver_ids():
            for signal, s in items:
                receivers, receiver_args = s
                for receiver in receivers:
                    yield id(receiver)
        for receiver_id in all_receiver_ids():
            print 'killing back ref', receiver_id, sender_id
            _kill_back_ref(receiver_id, sender_id)


def _remove_old_back_refs(sender_id, signal, receiver, receivers,
                          receiver_args):
    """Kill old ``senders_back`` references from ``receiver``.

    This guards against multiple registration of the same receiver for
    a given signal and sender leaking memory as old back reference
    records build up.

    Also removes old receiver instance from receivers.
    """
    try:
        index = receivers.index(receiver)
        # need to scan back references here and remove sender_id
    except ValueError:
        return False
    else:
        old_receiver = receivers[index]
        del receivers[index]
        del receiver_args[index]
        found = 0
        signals = connections.get(signal)
        if signals is not None:
            for sig, recs in connections.get(signal, {}).iteritems():
                if sig != signal:
                    for rec in recs:
                        if rec is old_receiver:
                            found = 1
                            break
        if not found:
            print 'killing back ref', id(receiver), sender_id
            _kill_back_ref(id(receiver), sender_id)
            return True
        return False
        
        
def _kill_back_ref(receiver_id, sender_id):
    """Do actual removal of back reference from ``receiver`` to
    ``sender_id``."""
    s = senders_back.get(receiver_id, ())
    while sender_id in s:
        try:
            s.remove(sender_id)
        except:
            print 'could not remove', sender_id, 'from', s
            break
    if not s:
        try:
            del senders_back[receiver_id]
        except KeyError:
            print 'could not del senders_back[', receiver_id, ']'
            print senders_back
            pass
    return True

    
