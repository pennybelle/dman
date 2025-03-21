# this script/program is a WIP and the code isnt great
# but i plan to put a lot into this and i'll learn as i go
# please consider contributing to the project by opening a PR

# my goal is to have a CLI-only menu-based program that can be scaled
# to maange and run as many servers as your hardware can handle.
# i have 4 years of experience dealing with dayz's weirdness and im hoping
# to use that experience to make other people's lives a bit easier

import asyncio
import logging

from __init__ import main, shutdown_servers

log = logging.getLogger(__name__)

## LEVELS ##
# 10: DEBUG
# 20: INFO
# 30: WARNING
# 40: ERROR
# 50: CRITICAL

# log.debug("This is a debug log")
# log.info("This is an info log")
# log.warning("This is a warn log")
# log.critical("This is a criticallog")

log.info("######################## STARTING FROM THE TOP ########################")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    server_instances = None
    main_task = None

    try:
        # Run the main task
        main_task = loop.create_task(main())
        server_instances = loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        # This runs when Ctrl+C is pressed
        log.info("Keyboard interrupt detected")
        if main_task and not main_task.done():
            # Cancel the main task if it's still running
            main_task.cancel()
            try:
                # Try to get the server instances if available
                server_instances = loop.run_until_complete(main_task)
            except asyncio.CancelledError:
                # This is expected when cancelling the task
                pass
    finally:
        # Run the shutdown procedure if we have server instances
        if server_instances:
            try:
                loop.run_until_complete(shutdown_servers(server_instances))
            except Exception as e:
                log.error(f"Error during shutdown: {e}")

        # Close all running event loop tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()

        # Allow cancelled tasks to complete with a timeout
        if pending:
            try:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            except asyncio.CancelledError:
                pass

        # Close the event loop
        loop.close()
