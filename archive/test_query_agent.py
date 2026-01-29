"""
Test script for the Query Agent
Run this to test natural language queries against the database
"""

from query_agent import query
import sys

def main():
    print("=" * 70)
    print("Legal Case Management System - Query Agent Test")
    print("=" * 70)
    print("\nEnter your queries in natural language (Arabic or English)")
    print("Type 'exit' or 'quit' to stop\n")
    
    if len(sys.argv) > 1:
        # Single query from command line
        user_query = " ".join(sys.argv[1:])
        print(f"Query: {user_query}")
        print("-" * 70)
        answer = query(user_query)
        print(f"\nAnswer:\n{answer}\n")
    else:
        # Interactive mode
        while True:
            try:
                user_query = input("\n> ").strip()
                
                if not user_query:
                    continue
                
                if user_query.lower() in ['exit', 'quit', 'q']:
                    print("Goodbye!")
                    break
                
                print("\nProcessing...")
                answer = query(user_query)
                print(f"\n{answer}\n")
                print("-" * 70)
                
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"\nError: {str(e)}")
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    main()

