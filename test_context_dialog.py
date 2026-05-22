#!/usr/bin/env python3
"""
Test script for context-aware dialog in Andromeda
Tests the example dialog from the user's request:
  User: салат
  Assistant: Классический салат! 🥗 Вкусный и полезный. Хотите, я расскажу тебе простой рецепт салата с авокадо и помидором?
  User: да
  Assistant: (should continue about salad recipe, NOT suggest news)
"""

import sys
import os
sys.path.insert(0, str(os.path.dirname(__file__)))

from core.context_manager import ContextManager

def test_context_dialog():
    """Test that context manager properly stores and retrieves dialog history"""
    print("Testing context-aware dialog...")
    
    # Create context manager instance
    cm = ContextManager()
    user_id = 12345  # Test user ID
    
    # Simulate the dialog from the example
    print("\n--- Simulating dialog ---")
    
    # Step 1: User says "салат"
    print("User: салат")
    cm.add_command(user_id, "салат")
    
    # Step 2: Assistant responds about salad
    assistant_response_1 = "Классический салат! 🥗 Вкусный и полезный. Хотите, я расскажу тебе простой рецепт салата с авокадо и помидором?"
    print(f"Assistant: {assistant_response_1}")
    cm.add_assistant_response(user_id, assistant_response_1)
    
    # Step 3: User says "да"
    print("User: да")
    cm.add_command(user_id, "да")
    
    # Test 1: Check conversation history
    print("\n--- Test 1: Conversation history ---")
    history = cm.get_conversation_history(user_id)
    print(f"History entries: {len(history)}")
    for entry in history:
        print(f"  [{entry['role']}]: {entry['content'][:50]}...")
    
    assert len(history) == 3, f"Expected 3 entries, got {len(history)}"
    assert history[0]['role'] == 'user', "First entry should be user"
    assert history[0]['content'] == 'салат', f"First content should be 'салат', got '{history[0]['content']}'"
    assert history[1]['role'] == 'assistant', "Second entry should be assistant"
    assert 'авокадо' in history[1]['content'], "Assistant response should mention avocado"
    assert history[2]['role'] == 'user', "Third entry should be user"
    assert history[2]['content'] == 'да', f"Third content should be 'да', got '{history[2]['content']}'"
    print("✓ Conversation history correctly stored")
    
    # Test 2: Check backward-compatible get_context
    print("\n--- Test 2: Backward-compatible get_context ---")
    context = cm.get_context(user_id)
    print(f"Context entries: {len(context)}")
    for entry in context:
        role = entry.get('role', 'unknown')
        cmd = entry.get('command', '')
        resp = entry.get('response', '')
        print(f"  [{role}]: command='{cmd[:30]}', response='{resp[:30]}'")
    
    assert len(context) == 3, f"Expected 3 context entries, got {len(context)}"
    print("✓ Backward-compatible context working")
    
    # Test 3: Check multimodal context
    print("\n--- Test 3: Multimodal context ---")
    mm_context = cm.get_multimodal_context(user_id)
    if mm_context:
        print(f"Time of day: {mm_context.get('time_of_day')}")
        print(f"Previous actions: {mm_context.get('previous_actions')}")
        print(f"User mood: {mm_context.get('user_mood')}")
        assert 'салат' in mm_context.get('previous_actions', []), \
            "Previous actions should contain 'салат'"
        print("✓ Multimodal context working")
    
    # Test 4: Simulate longer dialog
    print("\n--- Test 4: Longer dialog ---")
    cm2 = ContextManager()
    uid2 = 67890
    
    # Dialog: recipe request -> recipe -> thanks -> next request
    cm2.add_command(uid2, "рецепт пасты")
    cm2.add_assistant_response(uid2, "Конечно! Вот простой рецепт пасты карбонара...")
    cm2.add_command(uid2, "спасибо")
    cm2.add_assistant_response(uid2, "Пожалуйста! Приятного аппетита! 🍝")
    cm2.add_command(uid2, "а как насчет десерта?")
    
    history2 = cm2.get_conversation_history(uid2)
    print(f"History entries: {len(history2)}")
    assert len(history2) == 5, f"Expected 5 entries, got {len(history2)}"
    
    # Check that "десерта" question has context of previous pasta conversation
    roles = [e['role'] for e in history2]
    assert roles == ['user', 'assistant', 'user', 'assistant', 'user'], \
        f"Roles should alternate, got {roles}"
    print("✓ Longer dialog with alternating roles working")
    
    # Test 5: Test max_entries limit
    print("\n--- Test 5: Max entries limit ---")
    # Create ContextManager with high max_commands for this test
    cm3 = ContextManager()
    cm3.max_commands = 100  # Override for testing
    uid3 = 11111
    
    # Add more than 20 entries
    for i in range(25):
        cm3.add_command(uid3, f"команда {i}")
        cm3.add_assistant_response(uid3, f"ответ {i}")
    
    history3 = cm3.get_conversation_history(uid3, max_entries=20)
    print(f"History with max_entries=20: {len(history3)} entries")
    assert len(history3) == 20, f"Expected 20 entries, got {len(history3)}"
    print("✓ Max entries limit working")
    
    print("\n🎉 All context dialog tests passed!")
    return True

def test_context_aware_interpretation():
    """Test context-aware command interpretation"""
    print("\nTesting context-aware interpretation...")
    
    cm = ContextManager()
    user_id = 99999
    
    # Add commands with youtube/video to build context
    cm.add_command(user_id, "открой youtube")
    cm.add_command(user_id, "смотри видео с котиками")
    
    # Test interpretation of "продолжи"
    interpretation = cm.get_context_aware_interpretation(user_id, "продолжи")
    print(f"Interpretation of 'продолжи': {interpretation}")
    
    # Should recognize continuation of video
    assert 'продолжи видео' in interpretation['interpreted_command'] or \
           'previous_video' in interpretation['context_factors'], \
        "Should interpret 'продолжи' as continuing video"
    print("✓ Context-aware interpretation working")
    
    return True

if __name__ == "__main__":
    try:
        test_context_dialog()
        test_context_aware_interpretation()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
